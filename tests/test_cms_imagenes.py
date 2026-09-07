"""Subida de imágenes desde el panel.

Lo que se comprueba, sobre todo, es lo que NO debe entrar: la persona que sube va a mandar
lo que le dé el móvil, y el endpoint está detrás de una contraseña compartida, así que la
validación tiene que aguantar tanto un descuido como un archivo malicioso renombrado.
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import api
import cms_imagenes
import database as db

client = TestClient(api.app)
_AUTH = ("test-admin", "test-pass")


@pytest.fixture(autouse=True)
def _galeria_limpia(monkeypatch, tmp_path):
    """Nunca se escribe en el directorio de subidas real.

    Hay que redirigir dos cosas, no una: dónde escribe cms_imagenes y desde dónde lee el
    StaticFiles montado en /uploads, que fijó su directorio al importar api.py y no lo
    vuelve a mirar."""
    destino = tmp_path / "uploads"
    destino.mkdir()
    monkeypatch.setattr(cms_imagenes, "UPLOADS_DIR", str(destino))

    mount = next(r for r in api.app.routes if getattr(r, "name", None) == "uploads")
    monkeypatch.setattr(mount.app, "directory", str(destino))
    monkeypatch.setattr(mount.app, "all_directories", [destino])

    conn = db.get_connection()
    conn.execute("DELETE FROM imagenes")
    conn.commit()
    conn.close()
    yield


def _png(ancho=800, alto=600, color=(255, 180, 61)):
    imagen = Image.new("RGB", (ancho, alto), color)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


def _subir(datos, nombre="foto.png", tipo="image/png"):
    return client.post("/api/cms/imagenes", auth=_AUTH,
                       files={"archivo": (nombre, datos, tipo)})


# --- Autenticación ---

def test_subir_exige_credenciales():
    assert client.post("/api/cms/imagenes", files={"archivo": ("f.png", _png(), "image/png")}).status_code == 401
    assert client.get("/api/cms/imagenes").status_code == 401
    assert client.delete("/api/cms/imagenes/x.webp").status_code == 401


# --- Camino feliz ---

def test_subir_un_png_lo_convierte_a_webp():
    r = _subir(_png())

    assert r.status_code == 200
    datos = r.json()
    assert datos["nombre_fichero"].endswith(".webp")
    assert datos["url"].startswith("/uploads/")


def test_una_foto_enorme_se_reduce_a_un_tamano_razonable():
    """Sin esto, una foto de móvil de 4000 px se publicaría tal cual y hundiría la página."""
    r = _subir(_png(ancho=4000, alto=3000))

    assert r.json()["ancho"] == cms_imagenes.ANCHO_MAXIMO
    assert r.json()["alto"] == 1200  # mantiene la proporción 4:3


def test_el_nombre_lleva_el_hash_del_contenido():
    """Es lo que permite cachear /uploads/ para siempre sin que una foto nueva se quede
    tapada por la vieja."""
    primera = _subir(_png(color=(1, 2, 3))).json()["nombre_fichero"]
    segunda = _subir(_png(color=(9, 9, 9))).json()["nombre_fichero"]

    assert primera != segunda


def test_subir_dos_veces_la_misma_foto_no_la_duplica():
    datos = _png()
    primera = _subir(datos).json()["nombre_fichero"]
    segunda = _subir(datos).json()["nombre_fichero"]

    assert primera == segunda
    assert len(client.get("/api/cms/imagenes", auth=_AUTH).json()["imagenes"]) == 1


def test_la_imagen_subida_se_puede_descargar():
    url = _subir(_png()).json()["url"]

    respuesta = client.get(url)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/webp"


def test_listar_y_borrar():
    nombre = _subir(_png()).json()["nombre_fichero"]
    assert len(client.get("/api/cms/imagenes", auth=_AUTH).json()["imagenes"]) == 1

    assert client.delete(f"/api/cms/imagenes/{nombre}", auth=_AUTH).status_code == 200
    assert client.get("/api/cms/imagenes", auth=_AUTH).json()["imagenes"] == []


# --- Lo que hay que rechazar ---

def test_un_archivo_de_texto_renombrado_a_png_se_rechaza():
    """La extensión y el Content-Type los pone quien sube: solo vale la firma del contenido."""
    r = _subir(b"esto no es una imagen, solo texto plano", nombre="trampa.png")

    assert r.status_code == 400
    assert "no es una imagen" in r.json()["detail"]


def test_un_svg_se_rechaza_aunque_sea_una_imagen_de_verdad():
    """Un SVG es XML, admite <script> dentro y se serviría desde nuestro propio dominio."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

    r = _subir(svg, nombre="logo.svg", tipo="image/svg+xml")

    assert r.status_code == 400


def test_un_archivo_demasiado_grande_se_rechaza_con_un_mensaje_util():
    enorme = b"\x89PNG\r\n\x1a\n" + b"\x00" * (cms_imagenes.MAX_BYTES + 1)

    r = _subir(enorme, nombre="enorme.png")

    assert r.status_code == 400
    detalle = r.json()["detail"]
    assert "MB" in detalle and "máximo" in detalle


def test_un_png_con_la_firma_correcta_pero_datos_corruptos_se_rechaza():
    r = _subir(b"\x89PNG\r\n\x1a\n" + b"basura" * 50, nombre="roto.png")

    assert r.status_code == 400
    assert "dañada" in r.json()["detail"]


def test_un_archivo_vacio_se_rechaza():
    assert _subir(b"", nombre="vacio.png").status_code == 400


# --- Nombres de fichero ---

def test_el_nombre_original_se_convierte_en_algo_seguro():
    r = _subir(_png(), nombre="../../../etc/passwd.png")

    nombre = r.json()["nombre_fichero"]
    assert "/" not in nombre and ".." not in nombre


def test_los_acentos_y_espacios_del_nombre_se_limpian():
    r = _subir(_png(), nombre="Instalación en Molina (2026).png")

    assert r.json()["nombre_fichero"].startswith("instalacion-en-molina-2026-")


def test_borrar_con_una_ruta_manipulada_no_sale_del_directorio():
    assert cms_imagenes.borrar("../../agencia.db") is False
