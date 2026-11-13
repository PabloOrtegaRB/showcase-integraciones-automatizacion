"""Proveedor de técnicos en terreno SIMULADO.

Acepta trabajos, falla a veces a propósito (para ejercitar los reintentos) y, cuando acepta un trabajo,
envía después avisos firmados (webhooks) al sistema de origen. No es un servicio real ni guarda datos.

Ejecutar:  uvicorn --factory proveedor_simulado.main:crear_proveedor --port 8202
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import SECRETO_DESARROLLO
from app.firma import cabeceras

TECNICOS_FICTICIOS = ["Técnico Demo A", "Técnico Demo B", "Técnico Demo C"]


@dataclass
class ConfigProveedor:
    secreto: str
    tasa_fallo: float = 0.3
    latencia_ms: tuple[int, int] = (40, 200)
    semilla: int | None = None
    enviar_webhooks: bool = True
    retraso_webhook_s: float = 1.5
    fallos_forzados: dict[str, int] | None = None  # código de orden → cuántas veces fallar con 503

    @staticmethod
    def desde_entorno() -> "ConfigProveedor":
        semilla = os.environ.get("SEMILLA")
        forzados = {}
        for par in filter(None, os.environ.get("FALLOS_FORZADOS", "").split(",")):
            codigo, veces = par.split(":")
            forzados[codigo.strip()] = int(veces)
        return ConfigProveedor(
            secreto=os.environ.get("SECRETO_WEBHOOK", SECRETO_DESARROLLO),
            tasa_fallo=float(os.environ.get("TASA_FALLO", "0.3")),
            semilla=int(semilla) if semilla else None,
            enviar_webhooks=os.environ.get("ENVIAR_WEBHOOKS", "true").lower() == "true",
            retraso_webhook_s=float(os.environ.get("RETRASO_WEBHOOK_S", "1.5")),
            fallos_forzados=forzados,
        )


class TrabajoEntrada(BaseModel):
    codigo: str = Field(min_length=4, max_length=20)
    servicio: str = Field(min_length=3, max_length=40)
    direccion: str = Field(min_length=5, max_length=200)
    prioridad: str = Field(min_length=3, max_length=10)
    url_webhook: str = Field(min_length=10, max_length=300)


def construir_webhook(secreto: str, tipo: str, codigo: str, referencia: str, tecnico: str | None = None) -> tuple[bytes, dict]:
    aviso = {
        "id_evento": uuid.uuid4().hex,
        "tipo": tipo,
        "codigo_orden": codigo,
        "referencia": referencia,
        "tecnico": tecnico,
        "ocurrido_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cuerpo = json.dumps(aviso).encode()
    return cuerpo, cabeceras(secreto, cuerpo)


def crear_proveedor(config: ConfigProveedor | None = None,
                    transporte_webhooks: httpx.BaseTransport | None = None) -> FastAPI:
    config = config or ConfigProveedor.desde_entorno()
    azar = random.Random(config.semilla)
    candado = threading.Lock()
    trabajos: dict[str, str] = {}
    fallos_pendientes = dict(config.fallos_forzados or {})

    app = FastAPI(title="Proveedor de terreno SIMULADO",
                  description="Servicio externo simulado para el proyecto demostrativo. No es un servicio real.")

    def enviar_avisos(trabajo: TrabajoEntrada, referencia: str) -> None:
        tecnico = azar.choice(TECNICOS_FICTICIOS)
        with httpx.Client(timeout=5.0, transport=transporte_webhooks) as http:
            for tipo in ("TECNICO_ASIGNADO", "TRABAJO_COMPLETADO"):
                time.sleep(config.retraso_webhook_s)
                cuerpo, encabezados = construir_webhook(config.secreto, tipo, trabajo.codigo, referencia, tecnico)
                try:
                    http.post(trabajo.url_webhook, content=cuerpo, headers=encabezados)
                except httpx.HTTPError:
                    pass  # el proveedor real reintentaría; la simulación solo lo omite

    @app.get("/v1/salud")
    def salud():
        return {"estado": "ok", "simulado": True}

    @app.post("/v1/trabajos", status_code=201)
    def crear_trabajo(trabajo: TrabajoEntrada, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        bajo, alto = config.latencia_ms
        if alto > 0:
            time.sleep(azar.uniform(bajo, alto) / 1000)
        clave = idempotency_key or trabajo.codigo
        with candado:
            if clave in trabajos:
                return JSONResponse(status_code=200, content={"referencia": trabajos[clave], "repetido": True})
            if "sin cobertura" in trabajo.direccion.lower():
                raise HTTPException(422, "Dirección fuera de la zona de cobertura del proveedor.")
            if fallos_pendientes.get(trabajo.codigo, 0) > 0:
                fallos_pendientes[trabajo.codigo] -= 1
                raise HTTPException(503, "Servicio temporalmente no disponible (falla forzada de la demostración).")
            if azar.random() < config.tasa_fallo:
                raise HTTPException(503, "Servicio temporalmente no disponible (falla simulada).")
            referencia = f"PRV-{len(trabajos) + 1:05d}"
            trabajos[clave] = referencia
        if config.enviar_webhooks:
            threading.Thread(target=enviar_avisos, args=(trabajo, referencia), daemon=True).start()
        return {"referencia": referencia}

    return app
