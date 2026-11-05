"""Preguntas frecuentes de /faq.

Antes vivían escritas dos veces dentro de faq.html: una en el acordeón <details> visible y
otra, palabra por palabra, dentro del JSON-LD FAQPage. Nada las mantenía sincronizadas, así
que editar una respuesta y olvidar la otra publicaba en Google unos rich results que no se
correspondían con lo que ponía la página. Ahora las dos salen del mismo bucle sobre la
tabla `faq`, y esto es solo el texto de partida.

Importante al editarlas: la sección FAQ de documentos/solsureste_base_conocimiento.txt es lo
que responde el chatbot, y NO se actualiza sola. Si cambia una respuesta aquí, hay que
tocarla también allí y reindexar (`python cargar_pdfs.py` + reiniciar el servidor).
"""

import database as db

MAX_PREGUNTA = 200
MAX_RESPUESTA = 1200

# Texto original, el que estaba escrito en faq.html antes del panel. Sirve de semilla la
# primera vez y de red de seguridad: si la tabla estuviera vacía, /faq sigue saliendo bien.
PREGUNTAS_ORIGINALES = [
    {
        "pregunta": "¿En qué zonas trabajáis?",
        "respuesta": "Solsureste Solar opera directamente en toda la Región de Murcia y toda la provincia de Alicante. Centramos nuestros recursos técnicos en esta zona para garantizar la máxima calidad en cada instalación.",
    },
    {
        "pregunta": "¿Cuánto cuesta una instalación de placas solares?",
        "respuesta": "No tenemos una tarifa cerrada pública: el presupuesto final exacto lo da el comercial asignado tras una llamada de asesoramiento y, si procede, una visita técnica al tejado. El estudio inicial es siempre gratuito.",
    },
    {
        "pregunta": "¿Trabajáis con subcontratas?",
        "respuesta": "No. Solsureste Solar usa personal y maquinaria propia al 100% para controlar la calidad total del proyecto, sin depender de terceros.",
    },
    {
        "pregunta": "¿Cuánto tardáis en hacer la instalación?",
        "respuesta": "Para una vivienda, los trabajos se inician en unas dos semanas y el plazo de ejecución normal es de dos días. Para instalaciones mayores, el plazo es más largo porque requiere proyecto técnico y depende de la licencia de obra del ayuntamiento.",
    },
    {
        "pregunta": "¿Debería poner baterías?",
        "respuesta": "Son interesantes si quieres respaldo ante cortes de luz. Si no es tu caso, como los excedentes ya se compensan en la factura, suele ser más rentable no ponerlas. Aun así, recomendamos un inversor híbrido preparado para añadirlas en el futuro sin coste adicional.",
    },
    {
        "pregunta": "¿Qué pasa con la energía que no autoconsumo?",
        "respuesta": "El sistema queda programado para verter los excedentes a la red pública. Esto deja un registro en el contador y tu compañía eléctrica te compensa esos kWh en la factura mensual.",
    },
    {
        "pregunta": "¿Hay deducciones fiscales por instalar placas solares?",
        "respuesta": "Sí. A nivel estatal hay una deducción en el IRPF de hasta el 40% del coste por mejora de la eficiencia energética de la vivienda (base máxima de 7.500 € y sujeta a requisitos y plazos). Además, algunas comunidades añaden su propia deducción autonómica: en la Región de Murcia puede llegar al 50% de la inversión según tu renta (tope de 7.000 €) y la Comunitat Valenciana también tiene la suya. A esto se suman las bonificaciones en el IBI de algunos ayuntamientos. Los porcentajes y requisitos dependen de tu caso y del año fiscal, así que conviene confirmarlo con tu asesor fiscal; nosotros te entregamos toda la documentación de la instalación para que puedas aplicarlas.",
    },
    {
        "pregunta": "¿Qué garantía ofrecéis?",
        "respuesta": "Ofrecemos una garantía de 25 años: rendimiento mínimo garantizado en los módulos solares y garantía de mano de obra. Si la instalación no produce lo que se promete, lo resolvemos nosotros.",
    },
    {
        "pregunta": "¿Por qué elegir Solsureste Solar?",
        "respuesta": "Solsureste Solar se creó en 1999 y mantiene el mismo CIF desde el principio. En un sector con tantas oscilaciones de mercado, eso es una garantía de seriedad y continuidad.",
    },
]


def sembrar_si_vacia() -> int:
    """Copia el texto original a la tabla la primera vez. Idempotente: si ya hay preguntas
    guardadas no toca nada, así que puede llamarse en cada arranque sin miedo."""
    if db.get_faq(solo_activas=False):
        return 0
    for p in PREGUNTAS_ORIGINALES:
        db.crear_faq(p["pregunta"], p["respuesta"])
    return len(PREGUNTAS_ORIGINALES)


def preguntas():
    """Las preguntas que se pintan en /faq (visible y JSON-LD, del mismo sitio)."""
    guardadas = db.get_faq(solo_activas=True)
    return guardadas if guardadas else PREGUNTAS_ORIGINALES


def validar(pregunta: str, respuesta: str) -> str | None:
    """Mensaje de error en castellano para mostrar tal cual en el panel, o None si vale."""
    if not pregunta or not pregunta.strip():
        return "La pregunta no puede quedarse vacía."
    if not respuesta or not respuesta.strip():
        return "La respuesta no puede quedarse vacía."
    if len(pregunta) > MAX_PREGUNTA:
        return f"La pregunta es demasiado larga (máximo {MAX_PREGUNTA} caracteres)."
    if len(respuesta) > MAX_RESPUESTA:
        return f"La respuesta es demasiado larga (máximo {MAX_RESPUESTA} caracteres)."
    return None
