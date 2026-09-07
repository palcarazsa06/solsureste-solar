"""Traducción automática ES→EN de los textos del panel de contenido.

Cuando alguien guarda un texto en español, la versión inglesa de la web se queda coja: es
una traducción manual e independiente (ver CLAUDE.md), así que un cambio en la home española
no llega a `/en` hasta que alguien lo traduce. Este módulo lo hace con el mismo GPT-4o-mini
que ya usa el chatbot, y marca el resultado como «pendiente de revisar» para que en el panel
se vea que lo escribió una máquina.

Dos reglas de diseño, ambas deliberadas:

1. **La traducción nunca puede bloquear el guardado en español.** Si OpenAI falla, tarda o
   no está configurada, el texto español ya está guardado y publicado; el inglés conserva lo
   que tuviera antes. Se avisa en el panel y hay un botón para reintentar.
2. **Las tablas no se traducen.** Las cifras cambian de formato entre idiomas (6.957,50 €
   frente a €6,957.50) y una traducción automática de números es la mejor forma de publicar
   un precio equivocado. La tabla inglesa se edita a mano.
"""

import os

from openai import OpenAI
from pydantic import BaseModel, Field

import cms_campos
from logging_config import get_logger

logger = get_logger(__name__)

# Cliente propio y síncrono: los endpoints del panel son funciones `def` normales (FastAPI
# las ejecuta en un hilo aparte), no corrutinas como el flujo del chat.
#
# max_retries=0 a propósito: aquí hay una persona esperando delante de un botón «Guardar».
# Los 2 reintentos con backoff que trae el SDK por defecto convierten un fallo de OpenAI en
# casi un minuto de espera, y lo que se está esperando es opcional — el texto español ya
# está publicado. Es mejor fallar en seguida y ofrecer el botón «Reintentar traducción».
_cliente = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=15.0, max_retries=0)

# Tipos que se traducen. `numero` se copia tal cual (25 años son 25 years) y `tabla` se
# excluye a propósito, ver el docstring del módulo.
TIPOS_TRADUCIBLES = ("texto", "texto_largo")


class _Traduccion(BaseModel):
    texto_en: str = Field(description="Traducción al inglés del texto, lista para publicarse en la web.")


_INSTRUCCIONES = """Eres el traductor de la web de Solsureste Solar, una empresa de instalación
de placas solares en Murcia y Alicante (España).

Traduce al inglés el texto que te den. Reglas estrictas:
- Traduce SOLO lo que te dan. No añadas información, no la quites, no expliques nada.
- Es texto de marketing de una web: que suene natural en inglés, no una traducción literal.
- Si el texto lleva **dos asteriscos** alrededor de algo, consérvalos exactamente igual en la
  traducción, rodeando la parte equivalente.
- Las cifras se mantienen, pero con formato inglés: 1.800 € pasa a €1,800 y 0,16 € a €0.16.
- Conserva los nombres propios de lugares (Murcia, Alicante, Lorca, Cartagena, Orihuela).
- No añadas comillas ni punto final si el original no los lleva."""


def traducir(texto: str, contexto: str = "") -> str | None:
    """Devuelve la traducción al inglés, o None si no se ha podido conseguir.

    Nunca lanza: quien llama está en mitad de un guardado que ya ha tenido éxito."""
    if not texto or not texto.strip():
        return None
    try:
        respuesta = _cliente.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _INSTRUCCIONES},
                {"role": "user", "content": f"{contexto}\n\nTexto a traducir:\n{texto}".strip()},
            ],
            response_format=_Traduccion,
        )
        traducido = respuesta.choices[0].message.parsed.texto_en.strip()
        return traducido or None
    except Exception as e:
        logger.warning(f"[CMS] No se pudo traducir al inglés: {e}")
        return None


def traducir_campo(clave: str, valor):
    """Traduce el valor de un campo concreto, respetando su tipo y su límite de longitud.

    Devuelve (valor_en, motivo). `valor_en` es None si no hay traducción que aplicar, y
    `motivo` explica por qué, en castellano y para mostrarlo en el panel."""
    definicion = cms_campos.campo(clave)
    if not definicion:
        return None, "Ese campo no existe."

    if definicion["tipo"] == "numero":
        # Un número es el mismo en los dos idiomas: se copia en vez de gastar una llamada.
        return valor, "Copiado a la web en inglés."

    if definicion["tipo"] not in TIPOS_TRADUCIBLES:
        return None, "Las tablas se editan a mano en cada idioma para no descuadrar las cifras."

    traducido = traducir(valor, contexto=f"Contexto: «{definicion['etiqueta']}» de la web.")
    if traducido is None:
        return None, "No se ha podido traducir ahora mismo. El texto en español sí se ha guardado."

    if len(traducido) > definicion["max_length"]:
        # Antes que publicar un texto que descuadra la maqueta, se deja el inglés como estaba.
        logger.warning(f"[CMS] Traducción de '{clave}' descartada por larga ({len(traducido)}).")
        return None, "La traducción salía demasiado larga. Revisa el texto inglés a mano."

    return traducido, "Traducido al inglés automáticamente — repásalo cuando puedas."
