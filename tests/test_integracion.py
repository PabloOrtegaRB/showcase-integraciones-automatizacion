from tests.ayudas import ORDEN


def _crear(cliente):
    return cliente.post("/api/ordenes", json=ORDEN).json()["codigo"]


def test_reintenta_fallas_transitorias_hasta_lograrlo(crear_cliente):
    cliente, proveedor = crear_cliente([503, "timeout", 201])
    codigo = _crear(cliente)
    orden = cliente.get(f"/api/ordenes/{codigo}").json()

    assert orden["estado"] == "ENVIADA"
    assert orden["intentos"] == 3
    assert [e["tipo"] for e in orden["eventos"]].count("ENVIO_FALLIDO") == 2
    assert len(proveedor.peticiones) == 3
    assert {p.headers["Idempotency-Key"] for p in proveedor.peticiones} == {codigo}


def test_agota_los_intentos_y_queda_en_error(crear_cliente):
    cliente, proveedor = crear_cliente([503, 503, 503])
    codigo = _crear(cliente)
    orden = cliente.get(f"/api/ordenes/{codigo}").json()

    assert orden["estado"] == "ERROR_INTEGRACION"
    assert orden["intentos"] == 3
    assert "503" in orden["ultimo_error"]
    assert "ENVIO_AGOTADO" in [e["tipo"] for e in orden["eventos"]]
    assert len(proveedor.peticiones) == 3


def test_un_rechazo_permanente_no_se_reintenta(crear_cliente):
    cliente, proveedor = crear_cliente([422])
    codigo = _crear(cliente)
    orden = cliente.get(f"/api/ordenes/{codigo}").json()

    assert orden["estado"] == "ERROR_INTEGRACION"
    assert orden["intentos"] == 1
    assert "ENVIO_RECHAZADO" in [e["tipo"] for e in orden["eventos"]]
    assert len(proveedor.peticiones) == 1


def test_el_reintento_manual_recupera_la_orden(crear_cliente):
    cliente, _ = crear_cliente([503, 503, 503, 201])
    codigo = _crear(cliente)
    assert cliente.get(f"/api/ordenes/{codigo}").json()["estado"] == "ERROR_INTEGRACION"

    respuesta = cliente.post(f"/api/ordenes/{codigo}/reintentar")
    assert respuesta.status_code == 202
    orden = cliente.get(f"/api/ordenes/{codigo}").json()
    assert orden["estado"] == "ENVIADA"
    assert orden["intentos"] == 1
    assert "REINTENTO_MANUAL" in [e["tipo"] for e in orden["eventos"]]


def test_no_se_reintenta_una_orden_ya_enviada(crear_cliente):
    cliente, _ = crear_cliente([201])
    codigo = _crear(cliente)
    respuesta = cliente.post(f"/api/ordenes/{codigo}/reintentar")
    assert respuesta.status_code == 409
    assert respuesta.headers["content-type"].startswith("application/problem+json")


def test_el_resumen_cuenta_estados_y_reintentos(crear_cliente):
    cliente, _ = crear_cliente([503, 201, 422])
    _crear(cliente)
    _crear(cliente)
    resumen = cliente.get("/api/resumen").json()

    assert resumen["total"] == 2
    assert resumen["entregadas_al_proveedor"] == 1
    assert resumen["con_error"] == 1
    assert resumen["fallas_transitorias"] == 1
    assert resumen["tasa_exito"] == 50.0
    assert resumen["promedio_intentos"] == 1.5
