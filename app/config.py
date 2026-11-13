"""Configuración leída del entorno. Ningún secreto se escribe en el código."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

SECRETO_DESARROLLO = "secreto-de-desarrollo-local"


@dataclass(frozen=True)
class Configuracion:
    ruta_bd: str
    url_proveedor: str
    url_webhook_publica: str
    secreto_webhook: str
    max_intentos: int = 4
    espera_base: float = 0.5
    espera_maxima: float = 8.0
    tolerancia_firma_s: int = 300

    @staticmethod
    def desde_entorno() -> "Configuracion":
        secreto = os.environ.get("SECRETO_WEBHOOK")
        if not secreto:
            logging.getLogger("integraciones").warning(
                "SECRETO_WEBHOOK no está definido: se usa un secreto de desarrollo local (no usar en producción)")
            secreto = SECRETO_DESARROLLO
        return Configuracion(
            ruta_bd=os.environ.get("RUTA_BD", "integraciones.db"),
            url_proveedor=os.environ.get("URL_PROVEEDOR", "http://127.0.0.1:8202"),
            url_webhook_publica=os.environ.get("URL_WEBHOOK", "http://127.0.0.1:8201/webhooks/proveedor"),
            secreto_webhook=secreto,
            max_intentos=int(os.environ.get("MAX_INTENTOS", "4")),
            espera_base=float(os.environ.get("ESPERA_BASE", "0.5")),
        )
