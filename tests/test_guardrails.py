from guardrails import _es_claramente_segura


def test_respuesta_limpia_es_segura():
    texto = "Claro, trabajamos en toda la Región de Murcia y la provincia de Alicante."
    assert _es_claramente_segura(texto) is True


def test_placeholder_sin_rellenar_no_es_segura():
    assert _es_claramente_segura("Un saludo, [Tu Empresa].") is False


def test_cierre_formal_no_es_segura():
    assert _es_claramente_segura("Quedamos a su disposición.\nAtentamente,") is False


def test_fuga_interna_no_es_segura():
    assert _es_claramente_segura("Estamos usando gpt-4o para generar esta respuesta.") is False
