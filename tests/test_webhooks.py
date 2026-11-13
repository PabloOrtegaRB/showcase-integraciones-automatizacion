from app.firma import cabeceras
from tests.ayudas import ORDEN, SECRETO, webhook


def _orden_enviada(crear_cliente):
    cliente, _ = crear_cliente([201])
    return cliente, cliente.post("/api/ordenes", json=ORDEN).json()["codigo"]


def test_avisos_validos_avanzan_el_estado(crear_cliente):
    cliente, codigo = _orden_enviada(crear_cliente)

    cuerpo, encabezados = webhook(codigo, "TECNICO_ASIGNADO", "evento-0001")
    respuesta = cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados)
    assert respuesta.status_code == 200 and respuesta.json()["nuevo_estado"] == "ASIGNADA"

    cuerpo, encabezados = webhook(codigo, "TRABAJO_COMPLETADO", "evento-0002")
    assert cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados).json()["nuevo_estado"] == "COMPLETADA"
    orden = cliente.get(f"/api/ordenes/{codigo}").json()
    assert orden["estado"] == "COMPLETADA"
    assert orden["tecnico"] == "Técnico Demo A"


def test_una_firma_invalida_se_rechaza_sin_cambios(crear_cliente):
    cliente, codigo = _orden_enviada(crear_cliente)
    cuerpo, encabezados = webhook(codigo, secreto="secreto-equivocado")

    respuesta = cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados)
    assert respuesta.status_code == 401
    assert respuesta.json()["title"] == "No autorizado"
    assert cliente.get(f"/api/ordenes/{codigo}").json()["estado"] == "ENVIADA"
    assert len(cliente.get("/api/eventos", params={"tipo": "WEBHOOK_RECHAZADO"}).json()) == 1


def test_una_marca_de_tiempo_vieja_se_rechaza(crear_cliente):
    cliente, codigo = _orden_enviada(crear_cliente)
    cuerpo, encabezados = webhook(codigo, marca=1_000_000)
    respuesta = cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados)
    assert respuesta.status_code == 401
    assert "tolerancia" in respuesta.json()["detail"]


def test_un_aviso_duplicado_es_idempotente(crear_cliente):
    cliente, codigo = _orden_enviada(crear_cliente)
    cuerpo, encabezados = webhook(codigo, "TECNICO_ASIGNADO", "evento-repetido")

    cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados)
    segunda = cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados)
    assert segunda.status_code == 200 and segunda.json()["estado"] == "duplicado"
    tipos = [e["tipo"] for e in cliente.get(f"/api/ordenes/{codigo}").json()["eventos"]]
    assert tipos.count("WEBHOOK_RECIBIDO") == 1
    assert tipos.count("WEBHOOK_DUPLICADO") == 1


def test_un_aviso_de_una_orden_inexistente_responde_404(crear_cliente):
    cliente, _ = crear_cliente()
    cuerpo, encabezados = webhook("OT-9999")
    assert cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados).status_code == 404


def test_un_aviso_que_no_aplica_al_estado_responde_409(crear_cliente):
    cliente, _ = crear_cliente([503, 503, 503])
    codigo = cliente.post("/api/ordenes", json=ORDEN).json()["codigo"]
    cuerpo, encabezados = webhook(codigo, "TRABAJO_COMPLETADO")
    assert cliente.post("/webhooks/proveedor", content=cuerpo, headers=encabezados).status_code == 409


def test_un_aviso_mal_formado_con_firma_valida_responde_422(crear_cliente):
    cliente, _ = crear_cliente()
    cuerpo = b'{"tipo": "OTRO"}'
    respuesta = cliente.post("/webhooks/proveedor", content=cuerpo, headers=cabeceras(SECRETO, cuerpo))
    assert respuesta.status_code == 422
    assert respuesta.json()["title"] == "Datos inválidos"
