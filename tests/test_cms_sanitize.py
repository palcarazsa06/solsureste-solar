"""Saneado del HTML del editor de artículos.

El cuerpo de un artículo es lo único del CMS que se inserta en una página pública sin
escapar, así que es la única superficie donde alguien podría colar etiquetas. Estos tests
fijan las dos mitades del contrato: que no pase nada peligroso, y que sí pase todo lo que
usan los artículos reales (si el saneador se comiera un `case-box`, publicaría el artículo
desmaquetado sin avisar).
"""
import pytest

import cms_sanitize
from cms_sanitize import sanear


# --- Lo que NO debe sobrevivir ---

@pytest.mark.parametrize("ataque", [
    "<script>alert(1)</script>",
    "<script src='https://malo.example/x.js'></script>",
    "<img src=x onerror=alert(1)>",
    "<a href=\"javascript:alert(1)\">pincha</a>",
    "<a href=\"JaVaScRiPt:alert(1)\">pincha</a>",
    "<iframe src='https://malo.example'></iframe>",
    "<object data='x'></object>",
    "<embed src='x'>",
    "<svg onload=alert(1)></svg>",
    "<style>body{display:none}</style>",
    "<form action='/x'><input name='p'></form>",
    "<meta http-equiv='refresh' content='0;url=https://malo.example'>",
    "<link rel='stylesheet' href='https://malo.example/x.css'>",
    "<base href='https://malo.example/'>",
    "<p onclick=\"alert(1)\">texto</p>",
    "<p onmouseover=alert(1)>texto</p>",
    "<div style=\"position:fixed;inset:0\">tapa la página</div>",
    "<img src=\"data:image/svg+xml;base64,PHN2Zz48c2NyaXB0Pg==\">",
    "<a href=\"data:text/html,<script>alert(1)</script>\">x</a>",
])
def test_los_ataques_clasicos_no_sobreviven(ataque):
    resultado = sanear(ataque)

    prohibido = ("<script", "<iframe", "<object", "<embed", "<svg", "<style", "<form",
                 "<meta", "<link", "<base", "onerror", "onclick", "onload", "onmouseover",
                 "javascript:", "data:", "style=")
    for marca in prohibido:
        assert marca not in resultado.lower(), f"{marca!r} sobrevivió en {resultado!r}"


def test_de_un_script_se_tira_tambien_lo_que_lleva_dentro():
    """No basta con quitar la etiqueta: si solo se quitara, el código quedaría publicado
    como texto suelto en mitad del artículo."""
    resultado = sanear("<p>Hola</p><script>alert(1)</script><p>Adiós</p>")

    assert resultado == "<p>Hola</p><p>Adiós</p>"


def test_del_css_pegado_tampoco_queda_rastro():
    resultado = sanear("<p>Hola</p><style>body{display:none}</style>")

    assert resultado == "<p>Hola</p>"


def test_las_imagenes_externas_se_descartan():
    """Además de filtrar la visita a otro servidor, la CSP img-src 'self' las bloquearía."""
    resultado = sanear('<img src="https://otro-sitio.example/foto.jpg" alt="x">')

    assert "otro-sitio.example" not in resultado


def test_solo_se_admiten_imagenes_propias():
    assert '/uploads/foto-a1b2c3d4.webp' in sanear('<img src="/uploads/foto-a1b2c3d4.webp" alt="a">')
    assert '/images/foto2.webp' in sanear('<img src="/images/foto2.webp" alt="a">')
    assert 'src=' not in sanear('<img src="//evil.example/x.png" alt="a">')


def test_las_clases_inventadas_se_descartan():
    """Una clase que no existe en el CSS dejaría el bloque sin estilo; una de la maqueta
    general podría descolocar la página entera."""
    resultado = sanear('<div class="case-box sss-hero-bg-cinematic inventada">x</div>')

    assert 'class="case-box"' in resultado
    assert "inventada" not in resultado and "sss-hero" not in resultado


def test_un_html_mal_anidado_no_se_traga_el_resto_de_la_pagina():
    """Pegar desde Word deja etiquetas sin cerrar continuamente."""
    resultado = sanear("<div class='case-box'><p>sin cerrar")

    assert resultado.count("<div") == resultado.count("</div>")
    assert resultado.count("<p") == resultado.count("</p>")


def test_un_cierre_suelto_no_rompe_nada():
    assert sanear("</div></p>texto") == "texto"


# --- Lo que SÍ debe pasar ---

def test_el_formato_normal_del_editor_se_conserva():
    entrada = ("<h2>Un titular</h2><p>Texto con <strong>negrita</strong> y "
               "<em>cursiva</em>.</p><ul><li>uno</li><li>dos</li></ul>")

    assert sanear(entrada) == entrada


def test_los_enlaces_internos_y_externos_validos_se_conservan():
    entrada = ('<p><a href="/placas-solares-lorca">Lorca</a> '
               '<a href="https://sede.gva.es">GVA</a> '
               '<a href="mailto:info@solsurestesolar.com">correo</a> '
               '<a href="tel:968869532">teléfono</a></p>')

    assert sanear(entrada) == entrada


def test_los_bloques_de_maqueta_de_los_articulos_se_conservan():
    entrada = ('<div class="case-box" data-reveal><p class="quote">"Muy bien."</p>'
               '<p class="who">— Antonio P.</p></div>')

    assert sanear(entrada) == entrada


def test_la_fila_de_cifras_se_conserva():
    entrada = ('<div class="stat-row" data-reveal><div class="stat-box">'
               '<p class="num">860 €</p><p class="lbl">Antes</p></div></div>')

    assert sanear(entrada) == entrada


def test_los_acentos_y_simbolos_no_se_estropean():
    assert sanear("<p>Ahorro de 1.800 € al año en la instalación</p>") == \
        "<p>Ahorro de 1.800 € al año en la instalación</p>"


def test_los_signos_de_menor_que_escritos_como_texto_se_escapan():
    resultado = sanear("<p>La amortización es < 6 años</p>")

    assert "&lt; 6 años" in resultado


def test_el_html_vacio_no_revienta():
    assert sanear("") == ""
    assert sanear(None) == ""


# --- La comprobación que más vale: contra el contenido real ---

# Trozo copiado literalmente de un artículo publicado (el caso de Cartagena). Va inline y no
# leído de la base de datos para que corra igual en CI, donde la base está vacía.
_ARTICULO_REAL = (
    '<div class="case-box" data-reveal>\n'
    '      <p class="quote">"Montaron dos instalaciones en mis naves industriales. '
    'Profesionalidad y cumplimiento de plazos impecables."</p>\n'
    '      <p class="who">— Antonio P., Cartagena (Murcia)</p>\n'
    '    </div>\n\n'
    '    <p data-reveal>Un año después de instalar autoconsumo industrial con Solsureste, '
    'la factura de ese mismo mes de verano bajó de 860 € a <strong>22 €</strong> —cargo fijo '
    'de potencia incluido—. En el cómputo anual, la instalación libera hoy más de 5.000 € que '
    'antes se iban directamente a la eléctrica.</p>\n\n'
    '    <div class="stat-row" data-reveal>\n'
    '      <div class="stat-box"><div class="num">860 € → 22 €</div>'
    '<div class="lbl">factura del mismo mes de verano</div></div>\n'
    '    </div>\n\n'
    '    <h2 data-reveal>Qué cambia en una nave industrial</h2>\n'
    '    <ul data-reveal><li>Menos coste fijo</li><li>Amortización más rápida</li></ul>\n'
    '    <p class="page-cta"><a class="btn-primary" href="/placas-solares-cartagena">'
    'Ver el caso completo</a></p>'
)


def test_un_articulo_real_pasa_intacto():
    """Si el saneador tocara el contenido que ya está publicado, republicar un artículo
    antiguo desde el panel lo desmaquetaría en silencio."""
    assert sanear(_ARTICULO_REAL) == _ARTICULO_REAL


def test_sanear_es_idempotente():
    """Guardar dos veces el mismo artículo no debe ir degradando el contenido."""
    entrada = '<div class="case-box"><p>x</p></div><script>alert(1)</script><p>y</p>'
    una_vez = sanear(entrada)

    assert sanear(una_vez) == una_vez
