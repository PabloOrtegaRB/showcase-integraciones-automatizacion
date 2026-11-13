"""API principal: órdenes de trabajo, webhooks del proveedor, registro de eventos y monitor web.

Ejecutar:  uvicorn --factory app.main:crear_app --port 8201
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import firma, registro
from app.bd import BaseDatos, Repositorio
from app.config import Configuracion
from app.integracion import ClienteProveedor, ServicioIntegracion
from app.modelos import TRANSICIONES_WEBHOOK, Estado, OrdenEntrada, WebhookEntrada

ESTATICOS = Path(__file__).parent / "estatico"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
TITULOS = {400: "Solicitud inválida", 401: "No autorizado", 404: "No encontrado", 405: "Método no permitido",
           409: "Conflicto con el estado actual", 422: "Datos inválidos"}
DETALLES_EN_INGLES = {"Not Found": "La ruta no existe.", "Method Not Allowed": "Método no permitido para esta ruta."}


def crear_app(config: Configuracion | None = None, transporte: httpx.BaseTransport | None = None,
              dormir: Callable[[float], None] = time.sleep) -> FastAPI:
    config = config or Configuracion.desde_entorno()
    log = registro.configurar()
    repo = Repositorio(BaseDatos(config.ruta_bd))
    integracion = ServicioIntegracion(repo, ClienteProveedor(config, transporte), config, dormir=dormir)

    app = FastAPI(
        title="Integraciones Valdora (demostrativa)",
        version="1.0.0",
        description="Órdenes de trabajo enviadas a un proveedor externo **simulado**, con reintentos controlados, "
                    "webhooks firmados con HMAC y registro de eventos. **Proyecto demostrativo — desarrollo propio, "
                    "no asociado a un cliente real.** Datos ficticios.")

    @app.middleware("http")
    async def cabeceras_de_seguridad(request: Request, call_next):
        respuesta = await call_next(request)
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("X-Frame-Options", "DENY")
        respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if not request.url.path.startswith(("/docs", "/redoc")):
            respuesta.headers.setdefault("Content-Security-Policy", CSP)
        return respuesta

    @app.exception_handler(StarletteHTTPException)
    async def error_http(request: Request, exc: StarletteHTTPException):
        detalle = DETALLES_EN_INGLES.get(str(exc.detail), str(exc.detail))
        return _problema(exc.status_code, TITULOS.get(exc.status_code, "Error"), detalle)

    @app.exception_handler(RequestValidationError)
    async def error_validacion(request: Request, exc: RequestValidationError):
        return _problema(422, "Datos inválidos", "La solicitud tiene campos inválidos.",
                         errores=[_traducir(e) for e in exc.errors()])

    @app.exception_handler(Exception)
    async def error_inesperado(request: Request, exc: Exception):
        log.exception("Error no controlado")
        return _problema(500, "Error interno", "Ocurrió un error inesperado. Intenta nuevamente.")

    @app.get("/salud", tags=["Operación"])
    def salud():
        return {"estado": "ok"}

    @app.post("/api/ordenes", status_code=201, tags=["Órdenes"],
              summary="Crea una orden y la envía al proveedor en segundo plano")
    def crear_orden(entrada: OrdenEntrada, tareas: BackgroundTasks, respuesta: Response):
        orden = repo.crear_orden(entrada.model_dump())
        tareas.add_task(integracion.procesar_envio, orden["codigo"])
        respuesta.headers["Location"] = f"/api/ordenes/{orden['codigo']}"
        return orden

    @app.get("/api/ordenes", tags=["Órdenes"], summary="Lista órdenes con filtros y paginación")
    def listar_ordenes(estado: Estado | None = None, q: str | None = Query(default=None, max_length=60),
                       limite: int = Query(default=20, ge=1, le=100), desplazamiento: int = Query(default=0, ge=0)):
        contenido, total = repo.listar(estado, q, limite, desplazamiento)
        return {"contenido": contenido, "total": total, "limite": limite, "desplazamiento": desplazamiento}

    @app.get("/api/ordenes/{codigo}", tags=["Órdenes"], summary="Obtiene una orden con su historial de eventos")
    def obtener_orden(codigo: str):
        orden = repo.obtener(codigo)
        if orden is None:
            raise HTTPException(404, f"No existe la orden {codigo}.")
        orden["eventos"] = repo.eventos(codigo=codigo, limite=100)
        return orden

    @app.post("/api/ordenes/{codigo}/reintentar", status_code=202, tags=["Órdenes"],
              summary="Reintenta manualmente una orden que agotó sus intentos")
    def reintentar(codigo: str, tareas: BackgroundTasks):
        orden = repo.obtener(codigo)
        if orden is None:
            raise HTTPException(404, f"No existe la orden {codigo}.")
        if orden["estado"] != "ERROR_INTEGRACION":
            raise HTTPException(409, f"Solo se reintentan órdenes con error de integración (estado actual: {orden['estado']}).")
        repo.actualizar(codigo, estado="PENDIENTE", intentos=0, ultimo_error=None)
        repo.registrar_evento(codigo, "REINTENTO_MANUAL", "Reintento solicitado por un operador")
        tareas.add_task(integracion.procesar_envio, codigo)
        return {"codigo": codigo, "estado": "PENDIENTE"}

    @app.get("/api/eventos", tags=["Registro"], summary="Registro de eventos de integración (más recientes primero)")
    def listar_eventos(tipo: str | None = Query(default=None, max_length=40), limite: int = Query(default=50, ge=1, le=200)):
        return repo.eventos(tipo=tipo, limite=limite)

    @app.get("/api/resumen", tags=["Registro"], summary="Indicadores para el monitor")
    def resumen():
        return repo.resumen()

    @app.post("/webhooks/proveedor", tags=["Webhooks"],
              summary="Recibe avisos firmados del proveedor (técnico asignado, trabajo completado)")
    async def recibir_webhook(request: Request):
        cuerpo = await request.body()
        valida, motivo = firma.verificar(config.secreto_webhook, request.headers.get("X-Marca-Tiempo"),
                                         request.headers.get("X-Firma"), cuerpo, config.tolerancia_firma_s)
        if not valida:
            repo.registrar_evento(None, "WEBHOOK_RECHAZADO", motivo)
            log.warning("Webhook rechazado", extra={"evento": "WEBHOOK_RECHAZADO"})
            raise HTTPException(401, motivo)
        try:
            aviso = WebhookEntrada.model_validate_json(cuerpo)
        except ValidationError as e:
            raise RequestValidationError(e.errors()) from e
        if repo.webhook_ya_recibido(aviso.id_evento):
            repo.registrar_evento(aviso.codigo_orden, "WEBHOOK_DUPLICADO", f"{aviso.tipo} ya procesado ({aviso.id_evento})")
            return {"estado": "duplicado", "orden": aviso.codigo_orden}
        orden = repo.obtener(aviso.codigo_orden)
        if orden is None:
            raise HTTPException(404, f"No existe la orden {aviso.codigo_orden}.")
        nuevo_estado = TRANSICIONES_WEBHOOK.get((orden["estado"], aviso.tipo))
        if nuevo_estado is None:
            raise HTTPException(409, f"El aviso {aviso.tipo} no aplica a una orden en estado {orden['estado']}.")
        repo.guardar_webhook(aviso.id_evento, aviso.codigo_orden, aviso.tipo)
        repo.actualizar(aviso.codigo_orden, estado=nuevo_estado, tecnico=aviso.tecnico or orden["tecnico"])
        repo.registrar_evento(aviso.codigo_orden, "WEBHOOK_RECIBIDO", f"{aviso.tipo} ({aviso.id_evento})")
        log.info("Webhook procesado", extra={"orden": aviso.codigo_orden, "estado": nuevo_estado, "evento": "WEBHOOK_RECIBIDO"})
        return {"estado": "procesado", "orden": aviso.codigo_orden, "nuevo_estado": nuevo_estado}

    app.mount("/estatico", StaticFiles(directory=ESTATICOS), name="estatico")

    @app.get("/", include_in_schema=False)
    def monitor():
        return FileResponse(ESTATICOS / "index.html")

    return app


def _problema(estado: int, titulo: str, detalle: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=estado, media_type="application/problem+json",
                        content={"type": "about:blank", "title": titulo, "status": estado, "detail": detalle, **extra})


def _traducir(error: dict) -> dict:
    ubicacion = [str(x) for x in error.get("loc", []) if x not in ("body", "query", "path")]
    ctx = error.get("ctx") or {}
    mensajes = {
        "missing": "Campo obligatorio.",
        "string_too_short": f"Debe tener al menos {ctx.get('min_length')} caracteres.",
        "string_too_long": f"Debe tener como máximo {ctx.get('max_length')} caracteres.",
        "literal_error": f"Valor no permitido. Opciones: {ctx.get('expected')}.",
        "greater_than_equal": f"Debe ser mayor o igual a {ctx.get('ge')}.",
        "less_than_equal": f"Debe ser menor o igual a {ctx.get('le')}.",
        "json_invalid": "El cuerpo no es un JSON válido.",
    }
    return {"campo": ".".join(ubicacion) or "cuerpo", "mensaje": mensajes.get(error.get("type", ""), error.get("msg", "Valor inválido."))}
