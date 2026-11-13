"""Modelos de entrada validados con Pydantic."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Servicio = Literal["MANTENCION_PREVENTIVA", "MANTENCION_CORRECTIVA", "CLIMATIZACION", "ELECTRICIDAD", "INSPECCION"]
Prioridad = Literal["BAJA", "MEDIA", "ALTA", "CRITICA"]
Estado = Literal["PENDIENTE", "ENVIADA", "ASIGNADA", "COMPLETADA", "ERROR_INTEGRACION"]
TipoWebhook = Literal["TECNICO_ASIGNADO", "TRABAJO_COMPLETADO"]


class OrdenEntrada(BaseModel):
    cliente: str = Field(min_length=3, max_length=120, examples=["Bodegas Arrayán Sur SpA"])
    direccion: str = Field(min_length=5, max_length=200, examples=["Av. Ejemplo 1234, Santiago"])
    servicio: Servicio
    prioridad: Prioridad = "MEDIA"
    descripcion: str | None = Field(default=None, max_length=500)


class WebhookEntrada(BaseModel):
    id_evento: str = Field(min_length=8, max_length=64)
    tipo: TipoWebhook
    codigo_orden: str = Field(min_length=4, max_length=20)
    referencia: str = Field(min_length=3, max_length=40)
    tecnico: str | None = Field(default=None, max_length=80)
    ocurrido_en: str | None = None


# Estado actual + tipo de webhook → nuevo estado (se acepta completar sin aviso previo de asignación).
TRANSICIONES_WEBHOOK: dict[tuple[str, str], str] = {
    ("ENVIADA", "TECNICO_ASIGNADO"): "ASIGNADA",
    ("ENVIADA", "TRABAJO_COMPLETADO"): "COMPLETADA",
    ("ASIGNADA", "TRABAJO_COMPLETADO"): "COMPLETADA",
}
