"""Registro (logs) en formato JSON, una línea por evento, sin datos personales."""
from __future__ import annotations

import json
import logging
import sys

CAMPOS_EXTRA = ("orden", "intento", "evento", "espera", "estado")


class FormatoJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        datos = {
            "momento": self.formatTime(registro, "%Y-%m-%dT%H:%M:%S"),
            "nivel": registro.levelname,
            "mensaje": registro.getMessage(),
        }
        for campo in CAMPOS_EXTRA:
            if hasattr(registro, campo):
                datos[campo] = getattr(registro, campo)
        return json.dumps(datos, ensure_ascii=False)


def configurar() -> logging.Logger:
    log = logging.getLogger("integraciones")
    if not log.handlers:
        salida = logging.StreamHandler(sys.stdout)
        salida.setFormatter(FormatoJson())
        log.addHandler(salida)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log
