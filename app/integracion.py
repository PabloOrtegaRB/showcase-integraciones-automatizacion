"""Envío de órdenes al proveedor externo con reintentos controlados."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable

import httpx

from app.bd import Repositorio
from app.config import Configuracion
from app.reintentos import espera

log = logging.getLogger("integraciones")


class ErrorTransitorio(Exception):
    """Falla que puede resolverse sola (5xx, 429, tiempo agotado, conexión): se reintenta."""


class ErrorPermanente(Exception):
    """El proveedor rechazó la orden (4xx): reintentar no sirve."""


class ClienteProveedor:
    """Cliente HTTP del proveedor de terreno. Usa Idempotency-Key para que un reintento no duplique el trabajo."""

    def __init__(self, config: Configuracion, transporte: httpx.BaseTransport | None = None):
        self._config = config
        self._http = httpx.Client(base_url=config.url_proveedor, timeout=5.0, transport=transporte)

    def crear_trabajo(self, orden: dict) -> str:
        cuerpo = {
            "codigo": orden["codigo"],
            "servicio": orden["servicio"],
            "direccion": orden["direccion"],
            "prioridad": orden["prioridad"],
            "url_webhook": self._config.url_webhook_publica,
        }
        try:
            respuesta = self._http.post("/v1/trabajos", json=cuerpo, headers={"Idempotency-Key": orden["codigo"]})
        except httpx.TimeoutException as e:
            raise ErrorTransitorio("Tiempo de espera agotado al contactar al proveedor") from e
        except httpx.TransportError as e:
            raise ErrorTransitorio(f"No se pudo conectar con el proveedor ({e.__class__.__name__})") from e
        if respuesta.status_code in (200, 201):
            return respuesta.json()["referencia"]
        if respuesta.status_code == 429 or respuesta.status_code >= 500:
            raise ErrorTransitorio(f"El proveedor respondió {respuesta.status_code}")
        raise ErrorPermanente(f"El proveedor rechazó la orden ({respuesta.status_code}): {_detalle(respuesta)}")

    def cerrar(self) -> None:
        self._http.close()


class ServicioIntegracion:
    def __init__(self, repo: Repositorio, cliente: ClienteProveedor, config: Configuracion,
                 dormir: Callable[[float], None] = time.sleep, aleatorio: Callable[[], float] = random.random):
        self._repo = repo
        self._cliente = cliente
        self._config = config
        self._dormir = dormir
        self._aleatorio = aleatorio

    def procesar_envio(self, codigo: str) -> None:
        orden = self._repo.obtener(codigo)
        if orden is None or orden["estado"] != "PENDIENTE":
            return
        maximo = self._config.max_intentos
        for intento in range(1, maximo + 1):
            self._repo.registrar_evento(codigo, "ENVIO_INTENTO", f"Intento {intento} de {maximo}")
            try:
                referencia = self._cliente.crear_trabajo(orden)
            except ErrorPermanente as e:
                self._repo.actualizar(codigo, estado="ERROR_INTEGRACION", intentos=intento, ultimo_error=str(e))
                self._repo.registrar_evento(codigo, "ENVIO_RECHAZADO", str(e))
                log.warning("Orden rechazada por el proveedor", extra={"orden": codigo, "intento": intento, "evento": "ENVIO_RECHAZADO"})
                return
            except ErrorTransitorio as e:
                self._repo.registrar_evento(codigo, "ENVIO_FALLIDO", f"Intento {intento}: {e}")
                if intento < maximo:
                    segundos = espera(intento, self._config.espera_base, self._config.espera_maxima, self._aleatorio)
                    log.info("Falla transitoria, se reintentará", extra={"orden": codigo, "intento": intento, "espera": segundos, "evento": "ENVIO_FALLIDO"})
                    self._dormir(segundos)
                    continue
                self._repo.actualizar(codigo, estado="ERROR_INTEGRACION", intentos=intento, ultimo_error=str(e))
                self._repo.registrar_evento(codigo, "ENVIO_AGOTADO", f"Se agotaron los {maximo} intentos")
                log.error("Intentos agotados", extra={"orden": codigo, "intento": intento, "evento": "ENVIO_AGOTADO"})
                return
            self._repo.actualizar(codigo, estado="ENVIADA", intentos=intento, referencia_externa=referencia, ultimo_error=None)
            self._repo.registrar_evento(codigo, "ENVIO_EXITOSO", f"Aceptada por el proveedor como {referencia} (intento {intento})")
            log.info("Orden enviada al proveedor", extra={"orden": codigo, "intento": intento, "evento": "ENVIO_EXITOSO"})
            return


def _detalle(respuesta: httpx.Response) -> str:
    try:
        return str(respuesta.json().get("detail", ""))[:200]
    except ValueError:
        return respuesta.text[:200]
