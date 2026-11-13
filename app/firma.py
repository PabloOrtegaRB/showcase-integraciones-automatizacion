"""Firma HMAC-SHA256 de webhooks, con marca de tiempo para evitar reenvíos (replay)."""
from __future__ import annotations

import hashlib
import hmac
import time


def firmar(secreto: str, marca_tiempo: int, cuerpo: bytes) -> str:
    mensaje = str(marca_tiempo).encode() + b"." + cuerpo
    return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()


def verificar(secreto: str, marca_tiempo: str | None, firma: str | None, cuerpo: bytes,
              tolerancia_s: int = 300, ahora: int | None = None) -> tuple[bool, str]:
    """Devuelve (válida, motivo). Compara en tiempo constante."""
    if not marca_tiempo or not firma:
        return False, "Faltan las cabeceras X-Marca-Tiempo o X-Firma."
    try:
        momento = int(marca_tiempo)
    except ValueError:
        return False, "La marca de tiempo no es válida."
    ahora = int(time.time()) if ahora is None else ahora
    if abs(ahora - momento) > tolerancia_s:
        return False, "La marca de tiempo está fuera de la tolerancia (posible reenvío)."
    if not hmac.compare_digest(firmar(secreto, momento, cuerpo), firma):
        return False, "La firma no es válida."
    return True, "ok"


def cabeceras(secreto: str, cuerpo: bytes, marca_tiempo: int | None = None) -> dict[str, str]:
    momento = int(time.time()) if marca_tiempo is None else marca_tiempo
    return {"Content-Type": "application/json", "X-Marca-Tiempo": str(momento), "X-Firma": firmar(secreto, momento, cuerpo)}
