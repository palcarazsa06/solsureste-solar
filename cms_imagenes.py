"""Subida de imágenes desde el panel de contenido.

Decisiones que conviene tener presentes al tocar esto:

- **Se guardan en `DATA_DIR/uploads/`, no en `static/`.** En Render `static/` se despliega
  desde git y es efímero: una foto subida ahí desaparecería en el siguiente deploy. `DATA_DIR`
  es el disco persistente, el mismo sitio donde vive `agencia.db`.
- **El nombre lleva el hash del contenido** (`portada-a1b2c3d4.webp`). `/uploads/` se sirve
  con `Cache-Control: immutable`, así que un fichero que cambiara de contenido conservando el
  nombre se quedaría cacheado una semana en los navegadores. Con el hash dentro, cambiar la
  imagen cambia la URL. De regalo, subir dos veces la misma foto no duplica el fichero.
- **Se reprocesa todo con Pillow y se guarda en WebP.** Quien sube va a mandar la foto tal
  cual sale del móvil (4000 px, 6 MB); publicarla así hunde el rendimiento de la página. Al
  reabrirla con Pillow, además, un fichero que no sea realmente una imagen revienta aquí y no
  llega nunca al disco.
- **SVG rechazado a propósito.** Es XML, admite `<script>` dentro y se sirve desde el propio
  dominio: sería un XSS almacenado servido desde solsurestesolar.com.
"""

import hashlib
import io
import os
import re
import unicodedata

from PIL import Image

import database as db
from logging_config import get_logger

logger = get_logger(__name__)

DATA_DIR = os.getenv("DATA_DIR", ".")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")

MAX_BYTES = 8 * 1024 * 1024        # 8 MB de entrada
ANCHO_MAXIMO = 1600                # suficiente para una portada a pantalla completa
CALIDAD_WEBP = 82

# Se comprueba el contenido real del fichero, no la extensión ni el Content-Type: los dos
# los pone quien sube y los dos se falsifican renombrando.
_FIRMAS = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
}


class ImagenInvalida(Exception):
    """Error con un mensaje ya redactado para enseñárselo a quien sube la foto."""


def _formato_real(datos: bytes) -> str | None:
    for firma, nombre in _FIRMAS.items():
        if datos.startswith(firma):
            return nombre
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "WEBP"
    return None


def slug(texto: str) -> str:
    """Nombre de fichero seguro a partir del nombre original que traía la imagen."""
    base = os.path.splitext(texto)[0]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return (base or "imagen")[:60]


def guardar(datos: bytes, nombre_original: str) -> dict:
    """Valida, reprocesa y guarda la imagen. Devuelve sus datos ya listos para el panel."""
    if not datos:
        raise ImagenInvalida("El archivo está vacío.")

    if len(datos) > MAX_BYTES:
        megas = len(datos) / 1024 / 1024
        raise ImagenInvalida(
            f"La imagen pesa {megas:.1f} MB y el máximo son {MAX_BYTES // 1024 // 1024} MB. "
            "Hazle una foto con menos calidad o redúcela antes de subirla."
        )

    if _formato_real(datos) is None:
        raise ImagenInvalida(
            "Ese archivo no es una imagen válida. Solo se admiten fotos JPG, PNG, GIF o WebP "
            "(los archivos SVG no se aceptan por seguridad)."
        )

    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except Exception:
        raise ImagenInvalida("La imagen está dañada y no se ha podido abrir.")

    # WebP no admite paletas ni canal alfa en algunos modos; RGB/RGBA cubre todos los casos.
    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGBA" if "A" in imagen.getbands() else "RGB")

    if imagen.width > ANCHO_MAXIMO:
        alto = round(imagen.height * ANCHO_MAXIMO / imagen.width)
        imagen = imagen.resize((ANCHO_MAXIMO, alto), Image.LANCZOS)

    salida = io.BytesIO()
    imagen.save(salida, format="WEBP", quality=CALIDAD_WEBP, method=6)
    procesada = salida.getvalue()

    # El hash es del fichero YA procesado: dos subidas de la misma foto acaban en el mismo
    # WebP y por tanto en el mismo nombre, sin duplicar nada en disco.
    firma = hashlib.sha256(procesada).hexdigest()[:8]
    nombre = f"{slug(nombre_original)}-{firma}.webp"

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    destino = os.path.join(UPLOADS_DIR, nombre)
    if not os.path.exists(destino):
        # Escritura atómica: si el proceso muere a mitad no queda un WebP truncado servido
        # como si fuera bueno (mismo patrón que el caché de reseñas).
        temporal = destino + ".tmp"
        with open(temporal, "wb") as f:
            f.write(procesada)
        os.replace(temporal, destino)

    db.registrar_imagen(nombre, nombre_original, len(procesada), imagen.width, imagen.height)
    logger.info(f"[CMS] Imagen subida: {nombre} ({len(procesada)} bytes, {imagen.width}px)")

    return {
        "nombre_fichero": nombre,
        "url": f"/uploads/{nombre}",
        "bytes": len(procesada),
        "ancho": imagen.width,
        "alto": imagen.height,
    }


def borrar(nombre_fichero: str) -> bool:
    """Elimina la imagen del disco y del registro.

    El nombre se vuelve a pasar por `basename` aunque venga de la base de datos: es lo que
    impide que un valor manipulado (`../../agencia.db`) escape del directorio de subidas."""
    seguro = os.path.basename(nombre_fichero)
    if seguro != nombre_fichero:
        return False
    ruta = os.path.join(UPLOADS_DIR, seguro)
    if os.path.exists(ruta):
        os.remove(ruta)
    db.borrar_imagen(seguro)
    return True


def listar() -> list:
    imagenes = db.get_imagenes()
    for imagen in imagenes:
        imagen["url"] = f"/uploads/{imagen['nombre_fichero']}"
    return imagenes
