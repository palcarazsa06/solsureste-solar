"""Motor de plantillas server-side del sitio público.

Las páginas que el panel de contenido puede editar (home ES/EN, FAQ, blog) se renderizan
con Jinja2 en cada petición, leyendo los textos de la base de datos. El resto del sitio
(páginas de ciudad, legales, 404) sigue siendo HTML estático servido por `StaticFiles`.

Por qué plantillas y no reescribir el HTML en disco (como hace `google_reviews.py` con el
`aggregateRating`): en Render `static/` se despliega desde git y es efímero — cualquier
cambio escrito ahí desaparece en el siguiente deploy. Con plantillas la base de datos es la
única fuente de verdad y el texto sigue llegando renderizado en el HTML servido, que es lo
que importa para SEO.

Las plantillas viven en `templates/`, FUERA de `static/`, por el mismo motivo que
`admin_panel/`: si estuvieran dentro, el `app.mount("/", StaticFiles(...))` las serviría en
crudo, con los `{{ }}` a la vista.
"""

import functools
import hashlib
import os

import jinja2
from fastapi.templating import Jinja2Templates

# Rutas relativas al CWD, igual que el resto del proyecto (`FileResponse("static/...")`).
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# autoescape va activado por defecto para .html: cualquier texto que venga de la base de
# datos se escapa solo, así que un `<script>` escrito en el panel no puede ejecutarse en la
# web pública. El HTML del cuerpo de los artículos del blog es la única excepción y pasa
# antes por el saneador (ver cms_sanitize.py).
# El Environment se construye a mano porque Jinja2Templates ya no acepta opciones sueltas.
# keep_trailing_newline: Jinja recorta por defecto el último salto de línea de la plantilla.
# Sin esto el HTML servido difiere del original en su último byte — inofensivo en sí, pero
# rompe cualquier comparación byte a byte contra la versión previa a la migración.
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    keep_trailing_newline=True,
)

# `| tojson` se usa para volcar texto dentro de bloques JSON-LD y de datos. Por defecto
# escaparía cada acento como ó, que es JSON válido pero deja el código fuente de la web
# ilegible. ensure_ascii=False lo evita sin perder la protección importante: Jinja escapa
# aparte < > & ' a < y compañía, que es lo que impide cerrar el <script> desde el texto.
_env.policies["json.dumps_kwargs"] = {"ensure_ascii": False, "sort_keys": True}

# Se registra tarde para evitar un import circular: cms importa database, que no depende
# de este módulo, pero mantener el import aquí abajo deja claro que es un añadido al env.
from cms import destacar  # noqa: E402

_env.filters["destacar"] = destacar

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@functools.lru_cache(maxsize=64)
def _huella(camino: str, mtime_ns: int) -> str:
    with open(camino, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:10]


def asset(ruta: str) -> str:
    """URL de un CSS/JS de static/ con la huella de su contenido: `/styles.css?v=1a2b3c4d`.

    Así el servidor puede pedir caché de un año para estos ficheros (ver `_CACHE_RULES` en
    api.py): cuando cambia el contenido cambia la URL, y nadie se queda con una versión vieja.
    La huella se recalcula solo si cambia la fecha de modificación del fichero (un `stat` por
    llamada): en local el servidor no se reinicia al editar un .css, y con una caché por
    proceso la página pedía el CSS nuevo con la URL vieja. Si el fichero no existe se devuelve
    la ruta sin versión en vez de romper la página.
    """
    camino = os.path.join(STATIC_DIR, ruta)
    try:
        return f"/{ruta}?v={_huella(camino, os.stat(camino).st_mtime_ns)}"
    except OSError:
        return f"/{ruta}"


_env.globals["asset"] = asset

templates = Jinja2Templates(env=_env)
