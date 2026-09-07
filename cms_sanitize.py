"""Saneado del HTML que escribe el editor del panel.

El cuerpo de un artículo es lo único que se inserta en una página pública sin escapar
(`{{ a.cuerpo_html | safe }}`), así que es la única superficie del CMS donde alguien podría
colar etiquetas. Aquí se filtra contra una lista blanca cerrada: **todo lo que no esté
explícitamente permitido se descarta**, no al revés.

Por qué la biblioteca estándar y no `bleach`/`nh3`:

- La lista de etiquetas es pequeña, cerrada y nuestra: no hay que cubrir el HTML entero.
- Se filtra con un parser de verdad (`html.parser`), nunca con expresiones regulares, que es
  el error clásico que hace inútiles a los saneadores caseros.
- Quien escribe ya está autenticado con la contraseña del panel. Esto es defensa en
  profundidad ante un copiar-pegar desde Word o una cuenta comprometida, no la frontera de
  seguridad principal, que es `verificar_admin`.

La lista blanca cubre lo que usan los artículos que ya existían (`case-box`, `stat-row`,
`page-cta`…) más lo que produce el editor. Si algún día hace falta un bloque nuevo, se añade
aquí y en el CSS de la plantilla; no se abre la puerta a HTML libre.
"""

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

# Etiqueta -> atributos permitidos en ella. Cualquier otra etiqueta o atributo se elimina.
ETIQUETAS = {
    "p": {"class", "data-reveal"},
    "br": set(),
    "strong": set(),
    "em": set(),
    "u": set(),
    "s": set(),
    "h2": {"class", "data-reveal"},
    "h3": {"class", "data-reveal"},
    "ul": {"class", "data-reveal"},
    "ol": {"class", "data-reveal"},
    "li": {"class"},
    "blockquote": {"class", "data-reveal"},
    "a": {"href", "class", "target", "rel"},
    "img": {"src", "alt", "width", "height", "loading", "class", "data-reveal"},
    "div": {"class", "data-reveal"},
    "span": {"class"},
}

# Etiquetas sin cierre: no llevan </...> y hay que emitirlas como <img ...>.
VACIAS = {"br", "img"}

# De estas no basta con quitar la etiqueta: también se tira lo que llevan dentro. Si no, un
# <script>alert(1)</script> pegado por error se queda como el texto suelto «alert(1)» en
# mitad del artículo — inofensivo, pero publicado a la vista de todos.
CONTENIDO_DESCARTADO = {"script", "style", "title", "textarea", "noscript", "template", "iframe"}

# Valores de `class` admitidos. Es lo que impide que se inventen clases que no existen en el
# CSS (el artículo saldría desmaquetado) o que se reutilicen clases de la maqueta general.
CLASES = {
    "case-box", "quote", "who",           # cita destacada de un cliente
    "stat-row", "stat-box", "num", "lbl",  # fila de cifras
    "page-cta", "btn-primary", "back-to-blog",
    "hero-cover", "hero-caption",
}

# Esquemas de enlace admitidos. Lo importante es lo que deja fuera: `javascript:` y `data:`.
ESQUEMAS = {"https", "mailto", "tel"}


def _href_seguro(valor: str) -> str | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if valor.startswith("/") and not valor.startswith("//"):
        return valor  # enlace interno
    if valor.startswith("#"):
        return valor
    try:
        esquema = urlparse(valor).scheme.lower()
    except ValueError:
        return None
    return valor if esquema in ESQUEMAS else None


def _src_seguro(valor: str) -> str | None:
    """Solo imágenes propias: las que se han subido por el panel o ya estaban en la web.

    Bloquea `data:` (donde cabe un SVG con script) y las URLs externas, que además de
    filtrar la visita a otro servidor romperían la CSP `img-src 'self'`."""
    valor = (valor or "").strip()
    if valor.startswith(("/uploads/", "/images/")) and not valor.startswith("//"):
        return valor
    return None


def _clases_seguras(valor: str) -> str | None:
    limpias = [c for c in (valor or "").split() if c in CLASES]
    return " ".join(limpias) if limpias else None


class _Saneador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.salida = []
        # Etiquetas abiertas y aceptadas, para saber qué cierres emitir: si se descarta un
        # <script>, su </script> tampoco debe salir.
        self._pila = []
        # Profundidad dentro de una etiqueta cuyo contenido se tira entero.
        self._silencio = 0

    def _atributos(self, tag, attrs):
        permitidos = ETIQUETAS[tag]
        partes = []
        for nombre, valor in attrs:
            nombre = nombre.lower()
            if nombre not in permitidos:
                continue
            if nombre == "data-reveal":
                partes.append(" data-reveal")
                continue
            if valor is None:
                continue
            if nombre == "href":
                valor = _href_seguro(valor)
            elif nombre == "src":
                valor = _src_seguro(valor)
            elif nombre == "class":
                valor = _clases_seguras(valor)
            elif nombre in ("width", "height"):
                valor = valor if valor.isdigit() else None
            elif nombre == "target":
                valor = valor if valor == "_blank" else None
            elif nombre == "rel":
                valor = valor if valor in ("noopener", "noreferrer", "noopener noreferrer") else None
            elif nombre == "loading":
                valor = valor if valor in ("lazy", "eager") else None
            if valor is None:
                continue
            partes.append(f' {nombre}="{escape(valor, quote=True)}"')
        return "".join(partes)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in CONTENIDO_DESCARTADO:
            self._silencio += 1
            return
        if self._silencio or tag not in ETIQUETAS:
            return
        marca = f"<{tag}{self._atributos(tag, attrs)}>"
        self.salida.append(marca)
        if tag not in VACIAS:
            self._pila.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if not self._silencio and tag in ETIQUETAS:
            self.salida.append(f"<{tag}{self._atributos(tag, attrs)}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in CONTENIDO_DESCARTADO:
            self._silencio = max(0, self._silencio - 1)
            return
        if self._silencio or tag in VACIAS or tag not in ETIQUETAS:
            return
        if tag in self._pila:
            # Se cierra todo lo que quedara abierto por debajo: un HTML mal anidado pegado
            # desde Word no debe poder dejar el resto de la página dentro de un <div>.
            while self._pila:
                abierta = self._pila.pop()
                self.salida.append(f"</{abierta}>")
                if abierta == tag:
                    break

    def handle_data(self, datos):
        if self._silencio:
            return
        self.salida.append(escape(datos, quote=False))

    def resultado(self) -> str:
        self.close()
        while self._pila:
            self.salida.append(f"</{self._pila.pop()}>")
        return "".join(self.salida)


def sanear(html: str) -> str:
    """Devuelve el HTML filtrado contra la lista blanca."""
    if not html:
        return ""
    saneador = _Saneador()
    saneador.feed(html)
    return saneador.resultado()
