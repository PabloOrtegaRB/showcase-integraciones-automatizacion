def test_el_monitor_carga_con_cabeceras_de_seguridad(crear_cliente):
    cliente, _ = crear_cliente()
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "Proyecto demostrativo" in respuesta.text
    assert "default-src 'self'" in respuesta.headers["content-security-policy"]
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert cliente.get("/estatico/monitor.js").status_code == 200


def test_la_documentacion_openapi_describe_la_api(crear_cliente):
    cliente, _ = crear_cliente()
    especificacion = cliente.get("/openapi.json").json()
    assert "/webhooks/proveedor" in especificacion["paths"]
    assert "Proyecto demostrativo" in especificacion["info"]["description"]


def test_salud(crear_cliente):
    cliente, _ = crear_cliente()
    assert cliente.get("/salud").json() == {"estado": "ok"}
