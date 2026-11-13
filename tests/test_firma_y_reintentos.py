from app.firma import cabeceras, verificar
from app.reintentos import espera

CUERPO = b'{"tipo":"TECNICO_ASIGNADO"}'


def test_una_firma_correcta_se_acepta():
    c = cabeceras("secreto", CUERPO, marca_tiempo=1_000)
    assert verificar("secreto", c["X-Marca-Tiempo"], c["X-Firma"], CUERPO, ahora=1_010) == (True, "ok")


def test_un_cuerpo_alterado_se_rechaza():
    c = cabeceras("secreto", CUERPO, marca_tiempo=1_000)
    valida, motivo = verificar("secreto", c["X-Marca-Tiempo"], c["X-Firma"], b'{"tipo":"OTRO"}', ahora=1_010)
    assert not valida and "firma" in motivo


def test_otro_secreto_se_rechaza():
    c = cabeceras("otro-secreto", CUERPO, marca_tiempo=1_000)
    assert verificar("secreto", c["X-Marca-Tiempo"], c["X-Firma"], CUERPO, ahora=1_010)[0] is False


def test_una_marca_de_tiempo_vieja_se_rechaza_para_evitar_reenvios():
    c = cabeceras("secreto", CUERPO, marca_tiempo=1_000)
    valida, motivo = verificar("secreto", c["X-Marca-Tiempo"], c["X-Firma"], CUERPO, tolerancia_s=300, ahora=1_301)
    assert not valida and "tolerancia" in motivo


def test_faltan_cabeceras_o_son_invalidas():
    assert verificar("secreto", None, None, CUERPO)[0] is False
    assert verificar("secreto", "no-es-numero", "abc", CUERPO)[0] is False


def test_la_espera_crece_en_forma_exponencial_con_tope():
    assert [espera(i, 0.5, 4.0, aleatorio=lambda: 0) for i in range(1, 6)] == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_la_variacion_es_de_hasta_25_por_ciento_y_sin_base_no_se_espera():
    assert espera(2, 1.0, 8.0, aleatorio=lambda: 1) == 2.5
    assert espera(3, 0, 8.0) == 0.0
