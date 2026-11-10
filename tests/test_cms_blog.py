"""Blog gestionado desde el panel: rutas públicas, borradores y sitemap.

El riesgo grande de este objetivo es de SEO: las URLs de los artículos terminan en `.html`
porque así estaban indexadas cuando eran ficheros sueltos, y el sitemap dejó de escribirse a
mano. Los tests fijan las dos cosas.
"""
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import api
import cms_blog
import database as db

client = TestClient(api.app)
_AUTH = ("test-admin", "test-pass")
_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@pytest.fixture(autouse=True)
def _blog_limpio():
    conn = db.get_connection()
    conn.execute("DELETE FROM articulos")
    conn.execute("DELETE FROM articulos_redirecciones")
    conn.commit()
    conn.close()
    yield


def _crear(slug="mi-articulo", titulo="Un artículo de prueba", publicado=True, **extra):
    datos = {
        "slug": slug,
        "titulo": titulo,
        "meta_description": "Descripción de prueba para el buscador.",
        "cuerpo_html": "<p>Contenido del artículo.</p>",
        "publicado": int(publicado),
        "publicado_en": "2026-08-01",
    }
    datos.update(extra)
    return db.crear_articulo(datos)


def _urls_del_sitemap():
    raiz = ET.fromstring(client.get("/sitemap.xml").text)
    return [u.find("s:loc", _NS).text for u in raiz.findall("s:url", _NS)]


# --- Siembra del contenido original ---
# Reproduce lo que pasa en Render: base de datos vacía en el disco persistente y los .html de
# los artículos ya no están en el repo. Si esto falla, las 3 URLs indexadas en Google se
# quedan en 404 nada más desplegar.

def test_con_la_base_vacia_se_siembran_los_articulos_originales():
    assert db.get_articulos(solo_publicados=False) == []

    creados = cms_blog.sembrar_si_vacia()

    assert creados == 3
    slugs = [a["slug"] for a in db.get_articulos(solo_publicados=False)]
    assert "autoconsumo-industrial-murcia-alicante-guia-empresas-2026" in slugs


def test_los_articulos_sembrados_responden_en_sus_urls_indexadas():
    cms_blog.sembrar_si_vacia()

    for slug in [a["slug"] for a in db.get_articulos()]:
        respuesta = client.get(f"/blog/articulos/{slug}.html")
        assert respuesta.status_code == 200, slug
        assert '"@type": "BlogPosting"' in respuesta.text
        assert "ai-disclosure" in respuesta.text


def test_la_siembra_del_blog_es_idempotente():
    assert cms_blog.sembrar_si_vacia() == 3
    assert cms_blog.sembrar_si_vacia() == 0
    assert len(db.get_articulos(solo_publicados=False)) == 3


def test_la_siembra_no_resucita_un_articulo_borrado_a_proposito():
    cms_blog.sembrar_si_vacia()
    borrado = db.get_articulos()[0]
    db.borrar_articulo(borrado["id"])

    cms_blog.sembrar_si_vacia()

    assert borrado["slug"] not in [a["slug"] for a in db.get_articulos(solo_publicados=False)]


def test_los_articulos_sembrados_conservan_su_fecha_real():
    """Fecharlos el día del despliegue le diría a Google que se han reescrito todos."""
    cms_blog.sembrar_si_vacia()

    fechas = {a["slug"]: a["publicado_en"] for a in db.get_articulos()}

    assert fechas["autoconsumo-industrial-murcia-alicante-guia-empresas-2026"] == "2026-09-03"
    assert cms_blog.hoy() not in fechas.values()


def test_el_sitemap_recien_desplegado_lleva_las_19_urls():
    cms_blog.sembrar_si_vacia()

    assert len(_urls_del_sitemap()) == 19


# --- Rutas públicas ---

def test_un_articulo_publicado_se_sirve_en_su_url_con_html():
    _crear()

    respuesta = client.get("/blog/articulos/mi-articulo.html")

    assert respuesta.status_code == 200
    assert "Un artículo de prueba" in respuesta.text
    assert "Contenido del artículo." in respuesta.text


def test_el_articulo_lleva_su_jsonld_y_el_aviso_de_ia():
    """El aviso de IA lo pone la plantilla, no el editor: nadie puede quitarlo sin querer."""
    _crear()

    html = client.get("/blog/articulos/mi-articulo.html").text

    assert '"@type": "BlogPosting"' in html
    assert '"BreadcrumbList"' in html
    assert "ai-disclosure" in html
    assert "inteligencia artificial" in html


def test_la_url_sin_html_redirige_a_la_canonica():
    _crear()

    respuesta = client.get("/blog/articulos/mi-articulo", follow_redirects=False)

    assert respuesta.status_code == 301
    assert respuesta.headers["location"] == "/blog/articulos/mi-articulo.html"


def test_un_articulo_inexistente_da_404():
    assert client.get("/blog/articulos/no-existe.html").status_code == 404


def test_el_indice_lista_los_articulos_por_fecha_descendente():
    """Antes el orden era manual y había dos artículos compartiendo fecha."""
    _crear(slug="viejo", titulo="El más viejo", publicado_en="2026-01-15")
    _crear(slug="nuevo", titulo="El más nuevo", publicado_en="2026-08-30")

    html = client.get("/blog").text

    assert html.index("El más nuevo") < html.index("El más viejo")


def test_el_indice_sin_articulos_no_se_rompe():
    html = client.get("/blog").text

    assert client.get("/blog").status_code == 200
    assert "Todavía no hay artículos" in html


# --- Borradores ---

def test_un_borrador_no_se_ve_en_publico():
    _crear(publicado=False)

    assert client.get("/blog/articulos/mi-articulo.html").status_code == 404


def test_un_borrador_no_aparece_en_el_indice_ni_en_el_sitemap():
    _crear(slug="borrador", titulo="Todavía sin terminar", publicado=False)

    assert "Todavía sin terminar" not in client.get("/blog").text
    assert not any("borrador" in u for u in _urls_del_sitemap())


def test_un_borrador_si_se_ve_en_la_vista_previa_con_credenciales():
    articulo_id = _crear(publicado=False)

    respuesta = client.get(f"/admin/preview/blog/{articulo_id}", auth=_AUTH)

    assert respuesta.status_code == 200
    assert "Un artículo de prueba" in respuesta.text


def test_la_vista_previa_exige_credenciales():
    articulo_id = _crear(publicado=False)

    assert client.get(f"/admin/preview/blog/{articulo_id}").status_code == 401


# --- Sitemap ---

def test_el_sitemap_es_xml_valido_y_lleva_las_paginas_fijas():
    urls = _urls_del_sitemap()

    assert len(urls) == len(api._SITEMAP_PAGINAS_FIJAS)
    assert "https://solsurestesolar.com/" in urls
    assert "https://solsurestesolar.com/placas-solares-murcia" in urls


def test_publicar_un_articulo_lo_mete_solo_en_el_sitemap():
    """Antes había que acordarse de añadir la URL a mano en static/sitemap.xml."""
    antes = len(_urls_del_sitemap())
    _crear()

    urls = _urls_del_sitemap()

    assert len(urls) == antes + 1
    assert "https://solsurestesolar.com/blog/articulos/mi-articulo.html" in urls


def test_el_lastmod_del_articulo_sale_de_su_fecha_real():
    _crear()
    db.actualizar_articulo(db.get_articulo_por_slug("mi-articulo")["id"], {"titulo": "Editado"})

    raiz = ET.fromstring(client.get("/sitemap.xml").text)
    entrada = next(u for u in raiz.findall("s:url", _NS)
                   if "mi-articulo" in u.find("s:loc", _NS).text)

    assert entrada.find("s:lastmod", _NS).text == cms_blog.hoy()


# --- Redirecciones al renombrar ---

def test_renombrar_un_articulo_deja_la_url_antigua_redirigiendo():
    """Cambiar el slug de un artículo indexado rompería su posición en Google."""
    articulo_id = _crear(slug="direccion-vieja")
    db.actualizar_articulo(articulo_id, {"slug": "direccion-nueva"})
    db.registrar_redireccion_articulo("direccion-vieja", "direccion-nueva")

    respuesta = client.get("/blog/articulos/direccion-vieja.html", follow_redirects=False)

    assert respuesta.status_code == 301
    assert respuesta.headers["location"] == "/blog/articulos/direccion-nueva.html"


def test_renombrar_dos_veces_no_encadena_redirecciones():
    """Google penaliza las cadenas de 301; la primera dirección debe apuntar ya a la última."""
    db.registrar_redireccion_articulo("uno", "dos")
    db.registrar_redireccion_articulo("dos", "tres")

    assert db.get_redireccion_articulo("uno") == "tres"


# --- Validación ---

def test_un_slug_con_acentos_o_espacios_se_rechaza():
    for malo in ("Mi Artículo", "con espacios", "MAYUS", "acentué"):
        assert cms_blog.validar({"titulo": "T", "slug": malo}) is not None


def test_no_se_puede_repetir_la_direccion_de_otro_articulo():
    _crear(slug="ocupado")

    error = cms_blog.validar({"titulo": "Otro", "slug": "ocupado"})

    assert error is not None and "Ya hay otro artículo" in error


def test_no_se_puede_publicar_sin_descripcion():
    error = cms_blog.validar({
        "titulo": "T", "slug": "t", "meta_description": "",
        "cuerpo_html": "<p>x</p>", "publicado": True,
    })

    assert error is not None and "descripción" in error


def test_no_se_puede_publicar_sin_contenido():
    error = cms_blog.validar({
        "titulo": "T", "slug": "t", "meta_description": "d",
        "cuerpo_html": "  ", "publicado": True,
    })

    assert error is not None


def test_el_slug_se_genera_a_partir_del_titulo():
    assert cms_blog.slugificar("¿Cuánto cuesta instalar placas en Molina?") == \
        "cuanto-cuesta-instalar-placas-en-molina"


def test_la_fecha_se_muestra_en_castellano():
    assert cms_blog.fecha_legible("2026-09-03") == "3 de septiembre de 2026"


# --- API del panel ---

_NUEVO = {
    "titulo": "Placas solares en una nave de Lorca",
    "meta_description": "Cómo bajó la factura de una nave industrial en Lorca.",
    "cuerpo_html": "<p>Contenido del artículo.</p>",
}


def test_los_endpoints_de_articulos_exigen_credenciales():
    assert client.get("/api/cms/articulos").status_code == 401
    assert client.post("/api/cms/articulos", json=_NUEVO).status_code == 401
    assert client.delete("/api/cms/articulos/1").status_code == 401


def test_crear_un_articulo_genera_su_direccion_desde_el_titulo():
    respuesta = client.post("/api/cms/articulos", auth=_AUTH, json=_NUEVO)

    assert respuesta.status_code == 200
    assert respuesta.json()["slug"] == "placas-solares-en-una-nave-de-lorca"


def test_un_articulo_creado_sin_publicar_nace_como_borrador():
    client.post("/api/cms/articulos", auth=_AUTH, json=_NUEVO)

    assert client.get("/blog/articulos/placas-solares-en-una-nave-de-lorca.html").status_code == 404


def test_publicar_desde_el_panel_lo_deja_visible_y_con_fecha_de_hoy():
    respuesta = client.post("/api/cms/articulos", auth=_AUTH, json={**_NUEVO, "publicado": True})
    slug = respuesta.json()["slug"]

    assert client.get(f"/blog/articulos/{slug}.html").status_code == 200
    assert db.get_articulo_por_slug(slug)["publicado_en"] == cms_blog.hoy()


def test_el_cuerpo_pasa_por_el_saneador_antes_de_guardarse():
    """Es lo único del CMS que luego se inserta en una página pública sin escapar."""
    respuesta = client.post("/api/cms/articulos", auth=_AUTH, json={
        **_NUEVO,
        "cuerpo_html": '<p>Bien</p><script>alert(1)</script><img src=x onerror=alert(1)>',
        "publicado": True,
    })
    slug = respuesta.json()["slug"]

    guardado = db.get_articulo_por_slug(slug)["cuerpo_html"]
    assert "<script>" not in guardado and "onerror" not in guardado
    assert "<p>Bien</p>" in guardado

    html = client.get(f"/blog/articulos/{slug}.html").text
    assert "<script>alert(1)</script>" not in html


def test_editar_un_articulo_actualiza_la_web():
    articulo_id = client.post("/api/cms/articulos", auth=_AUTH,
                              json={**_NUEVO, "publicado": True}).json()["id"]

    client.put(f"/api/cms/articulos/{articulo_id}", auth=_AUTH, json={
        **_NUEVO, "publicado": True, "cuerpo_html": "<p>Texto corregido.</p>",
    })

    html = client.get("/blog/articulos/placas-solares-en-una-nave-de-lorca.html").text
    assert "Texto corregido." in html


def test_renombrar_desde_el_panel_registra_el_301_automaticamente():
    """Sin esto, cambiar el título de un artículo publicado tiraría a la basura su posición
    en Google, y quien edita no tendría forma de saberlo."""
    articulo_id = client.post("/api/cms/articulos", auth=_AUTH,
                              json={**_NUEVO, "publicado": True}).json()["id"]

    client.put(f"/api/cms/articulos/{articulo_id}", auth=_AUTH, json={
        **_NUEVO, "titulo": "Otro título", "slug": "direccion-nueva", "publicado": True,
    })

    respuesta = client.get("/blog/articulos/placas-solares-en-una-nave-de-lorca.html",
                           follow_redirects=False)
    assert respuesta.status_code == 301
    assert respuesta.headers["location"] == "/blog/articulos/direccion-nueva.html"


def test_renombrar_un_borrador_no_deja_redireccion_basura():
    """Un borrador nunca estuvo indexado: no hay nada que redirigir."""
    articulo_id = client.post("/api/cms/articulos", auth=_AUTH, json=_NUEVO).json()["id"]

    client.put(f"/api/cms/articulos/{articulo_id}", auth=_AUTH,
               json={**_NUEVO, "slug": "otra-direccion"})

    assert db.get_redireccion_articulo("placas-solares-en-una-nave-de-lorca") is None


def test_no_se_puede_crear_un_articulo_con_una_direccion_ya_usada():
    client.post("/api/cms/articulos", auth=_AUTH, json=_NUEVO)

    respuesta = client.post("/api/cms/articulos", auth=_AUTH, json=_NUEVO)

    assert respuesta.status_code == 400
    assert "Ya hay otro artículo" in respuesta.json()["detail"]


def test_publicar_sin_descripcion_se_rechaza_con_un_mensaje_claro():
    respuesta = client.post("/api/cms/articulos", auth=_AUTH,
                            json={**_NUEVO, "meta_description": "", "publicado": True})

    assert respuesta.status_code == 400
    assert "descripción" in respuesta.json()["detail"]


def test_borrar_un_articulo_lo_quita_de_la_web_y_del_sitemap():
    articulo_id = client.post("/api/cms/articulos", auth=_AUTH,
                              json={**_NUEVO, "publicado": True}).json()["id"]

    client.delete(f"/api/cms/articulos/{articulo_id}", auth=_AUTH)

    assert client.get("/blog/articulos/placas-solares-en-una-nave-de-lorca.html").status_code == 404
    assert not any("nave-de-lorca" in u for u in _urls_del_sitemap())


def test_el_editor_quill_se_sirve_desde_el_propio_dominio_y_con_auth():
    """Va autoalojado porque la CSP (script-src 'self') descarta cualquier CDN sin avisar."""
    assert client.get("/admin/vendor/quill.js").status_code == 401
    assert client.get("/admin/vendor/quill.js", auth=_AUTH).status_code == 200
    assert client.get("/admin/vendor/quill.snow.css", auth=_AUTH).status_code == 200


# --- llms.txt (auditoría 2026-11) ---
# Era un fichero estático que se quedó con 3 artículos cuando ya había 5 publicados.

def test_llms_txt_lista_los_publicados_y_no_los_borradores():
    _crear(slug="publicado-ia", titulo="Artículo visible para IA")
    _crear(slug="borrador-ia", titulo="Borrador oculto", publicado=False)

    r = client.get("/llms.txt")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "[Artículo visible para IA](https://solsurestesolar.com/blog/articulos/publicado-ia.html)" in r.text
    assert "Borrador oculto" not in r.text


def test_llms_txt_conserva_el_texto_fijo_y_no_deja_marcas_de_plantilla():
    texto = client.get("/llms.txt").text
    assert texto.startswith("# Solsureste Solar")
    assert "## Datos citables" in texto and "## Contacto" in texto
    assert "{%" not in texto and "{{" not in texto and "{#" not in texto
