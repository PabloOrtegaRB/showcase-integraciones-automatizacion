import json
import time

import httpx
from fastapi.testclient import TestClient

from app.firma import verificar
from proveedor_simulado.main import ConfigProveedor, construir_webhook, crear_proveedor

TRABAJO = {"codigo": "OT-0001", "servicio": "CLIMATIZACION", "direccion": "Av. Ejemplo 1234, Santiago",
           "prioridad": "ALTA", "url_webhook": "http://api.prueba/webhooks/proveedor"}


def _proveedor(tasa_fallo=0.0, enviar_webhooks=False, transporte=None):
    config = ConfigProveedor(secreto="s", tasa_fallo=tasa_fallo, latencia_ms=(0, 0),
                             enviar_webhooks=enviar_webhooks, retraso_webhook_s=0)
    return TestClient(crear_proveedor(config, transporte_webhooks=transporte))


def test_acepta_un_trabajo_y_respeta_la_clave_de_idempotencia():
    proveedor = _proveedor()
    primera = proveedor.post("/v1/trabajos", json=TRABAJO, headers={"Idempotency-Key": "OT-0001"})
    segunda = proveedor.post("/v1/trabajos", json=TRABAJO, headers={"Idempotency-Key": "OT-0001"})
    assert primera.status_code == 201
    assert segunda.status_code == 200 and segunda.json()["repetido"] is True
    assert segunda.json()["referencia"] == primera.json()["referencia"]


def test_rechaza_direcciones_sin_cobertura():
    respuesta = _proveedor().post("/v1/trabajos", json={**TRABAJO, "direccion": "Sin cobertura, Camino Rural s/n"})
    assert respuesta.status_code == 422


def test_simula_fallas_transitorias():
    assert _proveedor(tasa_fallo=1.0).post("/v1/trabajos", json=TRABAJO).status_code == 503


def test_las_fallas_forzadas_se_agotan_y_luego_acepta():
    config = ConfigProveedor(secreto="s", tasa_fallo=0, latencia_ms=(0, 0), enviar_webhooks=False,
                             fallos_forzados={"OT-0001": 2})
    proveedor = TestClient(crear_proveedor(config))
    codigos = [proveedor.post("/v1/trabajos", json=TRABAJO).status_code for _ in range(3)]
    assert codigos == [503, 503, 201]


def test_los_avisos_salientes_van_firmados():
    cuerpo, encabezados = construir_webhook("s", "TECNICO_ASIGNADO", "OT-0001", "PRV-00001", "Técnico Demo A")
    assert verificar("s", encabezados["X-Marca-Tiempo"], encabezados["X-Firma"], cuerpo)[0] is True


def test_envia_los_dos_avisos_al_sistema_de_origen():
    recibidos: list[httpx.Request] = []

    def destino(request):
        recibidos.append(request)
        return httpx.Response(200, json={})

    _proveedor(enviar_webhooks=True, transporte=httpx.MockTransport(destino)).post("/v1/trabajos", json=TRABAJO)
    for _ in range(200):
        if len(recibidos) >= 2:
            break
        time.sleep(0.01)
    assert [json.loads(r.content)["tipo"] for r in recibidos] == ["TECNICO_ASIGNADO", "TRABAJO_COMPLETADO"]
    assert all(verificar("s", r.headers["X-Marca-Tiempo"], r.headers["X-Firma"], r.content)[0] for r in recibidos)
