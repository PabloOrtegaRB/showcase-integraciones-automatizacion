"""Ayudas compartidas por las pruebas: proveedor guionado, orden de ejemplo y avisos firmados."""
import json

import httpx

from app.firma import cabeceras

SECRETO = "secreto-de-pruebas"

ORDEN = {
    "cliente": "Bodegas Arrayán Sur SpA",
    "direccion": "Av. Ejemplo 1234, Santiago",
    "servicio": "CLIMATIZACION",
    "prioridad": "ALTA",
}


class ProveedorGuionado:
    """Transporte httpx falso: responde según un guion de códigos HTTP; «timeout» simula un tiempo agotado."""

    def __init__(self, guion=()):
        self.guion = list(guion)
        self.peticiones: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        paso = self.guion.pop(0) if self.guion else 201
        if paso == "timeout":
            raise httpx.ConnectTimeout("tiempo agotado", request=request)
        if paso in (200, 201):
            return httpx.Response(paso, json={"referencia": "PRV-00001"})
        return httpx.Response(paso, json={"detail": "respuesta de prueba"})


def webhook(codigo: str, tipo: str = "TECNICO_ASIGNADO", id_evento: str = "evento-0001",
            secreto: str = SECRETO, marca: int | None = None) -> tuple[bytes, dict]:
    cuerpo = json.dumps({"id_evento": id_evento, "tipo": tipo, "codigo_orden": codigo,
                         "referencia": "PRV-00001", "tecnico": "Técnico Demo A"}).encode()
    return cuerpo, cabeceras(secreto, cuerpo, marca)
