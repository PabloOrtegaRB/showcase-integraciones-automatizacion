# Ejecución de demostración con procesos reales

Generado por `scripts/demo_capturas.py` el 2026-11-13 08:20. La API (puerto 8201) y el proveedor **simulado** (puerto 8202) corrieron como procesos separados y se comunicaron por HTTP. El proveedor simulado falla a propósito con una probabilidad del 30 %, y además se forzaron 3 fallas seguidas para OT-0008, para mostrar los intentos agotados y el reintento manual. Como las órdenes se procesan en paralelo, el resto del resultado cambia en cada ejecución. Se usó un secreto de webhooks aleatorio, válido solo durante la ejecución.

## Resultado

| Orden | Cliente (ficticio) | Estado final | Intentos | Referencia del proveedor |
|---|---|---|---|---|
| OT-0001 | Bodegas Arrayán Sur SpA | COMPLETADA | 1 | PRV-00001 |
| OT-0002 | Comercial Maitén Ltda. | COMPLETADA | 1 | PRV-00002 |
| OT-0003 | Distribuidora Lenga S.A. | COMPLETADA | 1 | PRV-00003 |
| OT-0004 | Logística Peumo Alto SpA | COMPLETADA | 2 | PRV-00004 |
| OT-0005 | Alimentos Coigüe Ltda. | COMPLETADA | 2 | PRV-00005 |
| OT-0006 | Clínica Quillay S.A. | COMPLETADA | 3 | PRV-00006 |
| OT-0007 | Colegio Canelo Norte SpA | ERROR_INTEGRACION | 1 | — |
| OT-0008 | Hotel Tralca Ltda. | COMPLETADA | 1 | PRV-00007 |

**Resumen:** 8 órdenes · 7 entregadas al proveedor · 1 con error de integración · 7 fallas transitorias reintentadas · tasa de éxito 87.5 % · promedio de 1.5 intentos.

Órdenes que agotaron sus intentos por fallas transitorias y se reintentaron a mano: OT-0008. La orden con dirección «Sin cobertura» fue rechazada por el proveedor (error permanente) y no se reintenta.

El aviso con firma falsa fue rechazado con HTTP 401.

## Eventos registrados

| Tipo | Cantidad |
|---|---|
| ENVIO_AGOTADO | 1 |
| ENVIO_EXITOSO | 7 |
| ENVIO_FALLIDO | 7 |
| ENVIO_INTENTO | 15 |
| ENVIO_RECHAZADO | 1 |
| ORDEN_CREADA | 8 |
| REINTENTO_MANUAL | 1 |
| WEBHOOK_RECHAZADO | 1 |
| WEBHOOK_RECIBIDO | 14 |

## Muestra del registro JSON de la API

```json
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Orden enviada al proveedor", "orden": "OT-0001", "intento": 1, "evento": "ENVIO_EXITOSO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Orden enviada al proveedor", "orden": "OT-0002", "intento": 1, "evento": "ENVIO_EXITOSO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0004", "intento": 1, "evento": "ENVIO_FALLIDO", "espera": 0.24}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Orden enviada al proveedor", "orden": "OT-0003", "intento": 1, "evento": "ENVIO_EXITOSO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0006", "intento": 1, "evento": "ENVIO_FALLIDO", "espera": 0.215}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0005", "intento": 1, "evento": "ENVIO_FALLIDO", "espera": 0.213}
{"momento": "2026-11-13T08:19:52", "nivel": "WARNING", "mensaje": "Orden rechazada por el proveedor", "orden": "OT-0007", "intento": 1, "evento": "ENVIO_RECHAZADO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0008", "intento": 1, "evento": "ENVIO_FALLIDO", "espera": 0.231}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Orden enviada al proveedor", "orden": "OT-0004", "intento": 2, "evento": "ENVIO_EXITOSO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Orden enviada al proveedor", "orden": "OT-0005", "intento": 2, "evento": "ENVIO_EXITOSO"}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0008", "intento": 2, "evento": "ENVIO_FALLIDO", "espera": 0.459}
{"momento": "2026-11-13T08:19:52", "nivel": "INFO", "mensaje": "Falla transitoria, se reintentará", "orden": "OT-0006", "intento": 2, "evento": "ENVIO_FALLIDO", "espera": 0.457}
```
