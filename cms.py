"""Capa de contenido: resuelve qué texto se pinta en cada hueco de las plantillas.

Une el registro de campos (cms_campos.CAMPOS, con los valores originales del código) con lo
que el personal haya guardado desde el panel (tabla `contenido`). Lo guardado gana; lo que
nunca se ha tocado sale del registro.
"""

import re

from markupsafe import Markup, escape

import cms_campos
import database as db

# Marcado mínimo para los párrafos: **así** sale en negrita clara. Es lo único que se les
# permite, y se convierte en el mismo HTML que ya usaba la web a mano, así que el resultado
# es idéntico al original. Cualquier otra cosa que escriban se escapa: no pueden colar
# etiquetas ni romper la maqueta aunque peguen HTML desde otro sitio.
_NEGRITA = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HTML_NEGRITA = '<strong style="color:#f4f3f0">\\1</strong>'


def destacar(texto) -> Markup:
    """Filtro de plantilla: escapa el texto y convierte **negritas**."""
    return Markup(_NEGRITA.sub(_HTML_NEGRITA, str(escape(texto))))


def contenido(idioma: str) -> dict:
    """Diccionario clave -> valor listo para la plantilla, para un idioma."""
    guardado = db.get_contenido(idioma)
    return {
        clave: guardado.get(clave, cms_campos.defecto(clave, idioma))
        for clave in cms_campos.CAMPOS
    }


def contenido_para_panel(idioma: str) -> list:
    """Los campos tal y como los necesita el panel: definición + valor actual + si está
    modificado respecto al original y si es una traducción pendiente de revisar."""
    guardado = db.get_contenido_meta(idioma)
    campos = []
    for clave, definicion in cms_campos.CAMPOS.items():
        fila = guardado.get(clave)
        campos.append({
            "clave": clave,
            "grupo": definicion["grupo"],
            "etiqueta": definicion["etiqueta"],
            "ayuda": definicion.get("ayuda", ""),
            "tipo": definicion["tipo"],
            "max_length": definicion["max_length"],
            "columnas": list(definicion.get("columnas", ())),
            "valor": fila["valor"] if fila else cms_campos.defecto(clave, idioma),
            "original": cms_campos.defecto(clave, idioma),
            "modificado": fila is not None,
            "revisar": fila["revisar"] if fila else False,
            "actualizado_en": fila["actualizado_en"] if fila else "",
        })
    return campos
