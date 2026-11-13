import json

from tests.ayudas import ORDEN


def test_crear_una_orden_la_envia_al_proveedor(crear_cliente):
    cliente, proveedor = crear_cliente([201])
    respuesta = cliente.post("/api/ordenes", json=ORDEN)

    assert respuesta.status_code == 201
    codigo = respuesta.json()["codigo"]
    assert respuesta.headers["location"] == f"/api/ordenes/{codigo}"
    orden = cliente.get(f"/api/ordenes/{codigo}").json()
    assert orden["estado"] == "ENVIADA"
    assert orden["intentos"] == 1
    assert orden["referencia_externa"] == "PRV-00001"
    assert [e["tipo"] for e in reversed(orden["eventos"])] == ["ORDEN_CREADA", "ENVIO_INTENTO", "ENVIO_EXITOSO"]
    enviada = proveedor.peticiones[0]
    assert enviada.headers["Idempotency-Key"] == codigo
    assert json.loads(enviada.content)["url_webhook"].endswith("/webhooks/proveedor")


def test_la_validacion_responde_problem_details_en_espanol(crear_cliente):
    cliente, proveedor = crear_cliente()
    respuesta = cliente.post("/api/ordenes", json={"cliente": "AB", "direccion": "x", "servicio": "OTRO"})

    assert respuesta.status_code == 422
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    errores = {e["campo"]: e["mensaje"] for e in respuesta.json()["errores"]}
    assert errores["cliente"] == "Debe tener al menos 3 caracteres."
    assert errores["direccion"] == "Debe tener al menos 5 caracteres."
    assert errores["servicio"].startswith("Valor no permitido")
    assert proveedor.peticiones == []


def test_listar_filtra_por_estado_y_pagina(crear_cliente):
    cliente, _ = crear_cliente([201, 422, 201])
    for i in range(3):
        cliente.post("/api/ordenes", json={**ORDEN, "cliente": f"Cliente de prueba {i}"})

    assert cliente.get("/api/ordenes", params={"estado": "ENVIADA"}).json()["total"] == 2
    assert cliente.get("/api/ordenes", params={"estado": "ERROR_INTEGRACION"}).json()["total"] == 1
    pagina = cliente.get("/api/ordenes", params={"limite": 2}).json()
    assert len(pagina["contenido"]) == 2 and pagina["total"] == 3
    assert cliente.get("/api/ordenes", params={"limite": 500}).status_code == 422


def test_orden_inexistente_y_ruta_desconocida(crear_cliente):
    cliente, _ = crear_cliente()
    respuesta = cliente.get("/api/ordenes/OT-9999")
    assert respuesta.status_code == 404
    assert respuesta.json()["title"] == "No encontrado"
    assert cliente.get("/no-existe").json()["detail"] == "La ruta no existe."
