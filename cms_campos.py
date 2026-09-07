"""Registro de campos editables desde el panel de contenido.

Es la ÚNICA fuente de verdad del CMS: el panel se pinta a partir de este diccionario y la
validación del backend usa exactamente los mismos límites, así que interfaz y servidor no
pueden divergir. Añadir un campo nuevo = añadir una entrada aquí y usarla en la plantilla.

`defecto` guarda el texto que estaba escrito en el HTML antes de la migración. La base de
datos solo almacena los valores que alguien ha cambiado; si una clave no está en la BD se
renderiza este valor. Consecuencia práctica: con la base de datos vacía la web sale
exactamente igual que antes del CMS, y "restaurar original" siempre tiene a dónde volver.

Tipos:
  texto        — una línea. Se escapa entero al renderizar.
  texto_largo  — párrafo. Admite **negrita** (ver filtro `destacar` en templates_engine).
  numero       — entero de los contadores animados de la home.
  tabla        — rejilla de valores; el valor se guarda como JSON (lista de listas).
"""

# --- Límites por tipo ---
# Un texto que se pase de largo no "rompe" la web, pero descuadra la maqueta (el H1 salta de
# línea, una celda ensancha la tabla). Los máximos están puestos con holgura sobre el texto
# actual, no al milímetro.
MAX_TEXTO = 300
MAX_TEXTO_LARGO = 1200

GRUPOS = (
    ("hero", "Portada", "Lo primero que ve quien entra en la web."),
    ("cifras", "Cifras y contadores", "Los números grandes de la barra de estadísticas y las tarjetas."),
    ("casos", "Resultados reales", "Los tres casos de clientes de la portada."),
    ("financiacion", "Financiación", "La tabla de ejemplos de financiación y sus notas legales."),
)

CAMPOS = {
    # --- Portada ---
    "hero_badge": {
        "grupo": "hero",
        "etiqueta": "Etiqueta superior",
        "ayuda": "La píldora naranja encima del titular.",
        "tipo": "texto",
        "max_length": MAX_TEXTO,
        # Se guarda el "&" tal cual, no la entidad HTML: quien edita escribe texto normal y
        # el escapado automático de la plantilla lo convierte en &amp; al renderizar.
        "defecto": {
            "es": "25 años · Murcia & Alicante · maquinaria propia",
            "en": "25 years · Murcia & Alicante · own machinery",
        },
    },
    "hero_h1": {
        "grupo": "hero",
        "etiqueta": "Titular principal",
        "ayuda": "El título grande. Las últimas palabras se configuran aparte, abajo.",
        "tipo": "texto",
        "max_length": MAX_TEXTO,
        "defecto": {
            "es": "Instalamos placas solares en Murcia y Alicante,",
            "en": "We install solar panels in Murcia and Alicante,",
        },
    },
    "hero_h1_destacado": {
        "grupo": "hero",
        "etiqueta": "Final del titular (en naranja brillante)",
        "ayuda": "Se pinta con el efecto dorado, justo detrás del titular.",
        "tipo": "texto",
        "max_length": 120,
        "defecto": {"es": "de principio a fin", "en": "start to finish"},
    },
    "hero_subtitulo": {
        "grupo": "hero",
        "etiqueta": "Párrafo de presentación",
        "tipo": "texto_largo",
        "max_length": MAX_TEXTO_LARGO,
        "defecto": {
            "es": "Instalamos placas solares para hogares y empresas, y desarrollamos huertos solares. Con maquinaria y recursos propios, gestionamos cada proyecto de principio a fin sin depender de terceros.",
            "en": "We install solar panels for homes and businesses, and develop solar farms. With our own machinery and resources, we manage every project start to finish without depending on third parties.",
        },
    },
    "hero_form_titulo": {
        "grupo": "hero",
        "etiqueta": "Título del formulario",
        "tipo": "texto",
        "max_length": 120,
        "defecto": {"es": "Solicita tu estudio gratuito", "en": "Request your free assessment"},
    },
    "hero_form_boton": {
        "grupo": "hero",
        "etiqueta": "Texto del botón de envío",
        "tipo": "texto",
        "max_length": 80,
        "defecto": {"es": "Solicitar estudio gratuito", "en": "Request free assessment"},
    },
    # --- Cifras ---
    "stat_1_valor": {
        "grupo": "cifras", "etiqueta": "Contador 1 — número", "tipo": "numero",
        "max_length": 10, "defecto": {"es": "25", "en": "25"},
    },
    "stat_1_texto": {
        "grupo": "cifras", "etiqueta": "Contador 1 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Años de experiencia", "en": "Years of experience"},
    },
    "stat_2_valor": {
        "grupo": "cifras", "etiqueta": "Contador 2 — número", "tipo": "numero",
        "max_length": 10, "defecto": {"es": "500", "en": "500"},
    },
    "stat_2_texto": {
        "grupo": "cifras", "etiqueta": "Contador 2 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Instalaciones realizadas", "en": "Installations completed"},
    },
    "stat_3_valor": {
        "grupo": "cifras", "etiqueta": "Contador 3 — número (MW)", "tipo": "numero",
        "max_length": 10, "defecto": {"es": "25", "en": "25"},
    },
    "stat_3_texto": {
        "grupo": "cifras", "etiqueta": "Contador 3 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Potencia instalada", "en": "Power installed"},
    },
    "stat_4_valor": {
        "grupo": "cifras", "etiqueta": "Contador 4 — número (%)", "tipo": "numero",
        "max_length": 10, "defecto": {"es": "100", "en": "100"},
    },
    "stat_4_texto": {
        "grupo": "cifras", "etiqueta": "Contador 4 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Recursos propios", "en": "Own resources"},
    },
    "tarjeta_1_valor": {
        "grupo": "cifras", "etiqueta": "Tarjeta 1 — cifra", "tipo": "texto",
        "max_length": 20, "defecto": {"es": "€0", "en": "€0"},
    },
    "tarjeta_1_texto": {
        "grupo": "cifras", "etiqueta": "Tarjeta 1 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Coste del estudio inicial", "en": "Cost of the initial assessment"},
    },
    "tarjeta_2_valor": {
        "grupo": "cifras", "etiqueta": "Tarjeta 2 — cifra", "tipo": "texto",
        "max_length": 20, "defecto": {"es": "−80%", "en": "−80%"},
    },
    "tarjeta_2_texto": {
        "grupo": "cifras", "etiqueta": "Tarjeta 2 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Reducción media en factura", "en": "Average bill reduction"},
    },
    "tarjeta_3_valor": {
        "grupo": "cifras", "etiqueta": "Tarjeta 3 — cifra", "tipo": "texto",
        "max_length": 20, "defecto": {"es": "5–7", "en": "5–7"},
    },
    "tarjeta_3_texto": {
        "grupo": "cifras", "etiqueta": "Tarjeta 3 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Años de amortización", "en": "Years to break even"},
    },
    "tarjeta_4_valor": {
        "grupo": "cifras", "etiqueta": "Tarjeta 4 — cifra", "tipo": "texto",
        "max_length": 20, "defecto": {"es": "25+", "en": "25+"},
    },
    "tarjeta_4_texto": {
        "grupo": "cifras", "etiqueta": "Tarjeta 4 — texto", "tipo": "texto",
        "max_length": 80, "defecto": {"es": "Años de vida útil", "en": "Years of service life"},
    },
    # --- Casos reales ---
    "caso_1_titulo": {
        "grupo": "casos", "etiqueta": "Caso 1 (Lorca) — título", "tipo": "texto",
        "max_length": 140,
        "defecto": {
            "es": "Aire acondicionado todo el día con factura cero",
            "en": "Air conditioning all day with a zero bill",
        },
    },
    "caso_1_texto": {
        "grupo": "casos", "etiqueta": "Caso 1 (Lorca) — descripción", "tipo": "texto_largo",
        "max_length": MAX_TEXTO_LARGO,
        "defecto": {
            "es": "Este cliente en Lorca recibió en agosto una factura con **coste de energía €0**. Respecto al año anterior ahorró €170 ese mes. Con el año completo libera cerca de **€1.800 anuales**, pudiendo encender el aire sin preocuparse.",
            "en": "This client in Lorca received an August bill with **€0 energy cost**. Compared with the previous year, they saved €170 that month. Over a full year they free up around **€1,800 annually**, able to run the AC without worrying.",
        },
    },
    "caso_2_titulo": {
        "grupo": "casos", "etiqueta": "Caso 2 (Cartagena) — título", "tipo": "texto",
        "max_length": 140,
        "defecto": {
            "es": "€5.000 liberados de la factura cada año",
            "en": "€5,000 freed up from the bill every year",
        },
    },
    "caso_2_texto": {
        "grupo": "casos", "etiqueta": "Caso 2 (Cartagena) — descripción", "tipo": "texto_largo",
        "max_length": MAX_TEXTO_LARGO,
        "defecto": {
            "es": "Esta empresa en Cartagena tenía una factura de €860 en verano. Un año después de la instalación esa factura **bajó a €22** (incluido el cargo fijo). Libera ahora **más de €5.000 anuales** que antes iban a la eléctrica.",
            "en": "This business in Cartagena had an €860 summer bill. One year after installation, that bill **dropped to €22** (fixed charge included). It now frees up **more than €5,000 a year** that used to go to the utility company.",
        },
    },
    "caso_3_titulo": {
        "grupo": "casos", "etiqueta": "Caso 3 (Orihuela) — título", "tipo": "texto",
        "max_length": 140,
        "defecto": {
            "es": "Amortización en 6 años en gran instalación agrícola",
            "en": "Payback in 6 years on a large agricultural installation",
        },
    },
    "caso_3_texto": {
        "grupo": "casos", "etiqueta": "Caso 3 (Orihuela) — descripción", "tipo": "texto_largo",
        "max_length": MAX_TEXTO_LARGO,
        "defecto": {
            "es": "Explotación en Orihuela (Alicante) con factura de bombeo de €3.100 en verano. Tras el huerto solar propio, esa factura cayó a €390 el año siguiente. La reducción de €2.700 supuso **amortizar en menos de 6 años**.",
            "en": "A farm in Orihuela (Alicante) with a €3,100 summer pumping bill. After installing its own solar farm, that bill fell to €390 the following year. The €2,700 reduction meant **paying it off in under 6 years**.",
        },
    },
    # --- Financiación ---
    "financiacion_tabla": {
        "grupo": "financiacion",
        "etiqueta": "Tabla de ejemplos de financiación",
        "ayuda": "Cada fila es un ejemplo de instalación. Se puede añadir y quitar filas.",
        "tipo": "tabla",
        "columnas": ("Potencia", "N.º placas", "Inversión", "Ahorro/mes", "Cuota", "Ahorro 10a", "Ahorro 25a"),
        "max_filas": 12,
        "max_length": 40,  # por celda
        "defecto": {
            "es": [
                ["5 kW", "10", "6.957,50 €", "103,85 €", "80,60 €", "3.687,09 €", "27.283,69 €"],
                ["6 kW", "12", "7.986,00 €", "124,62 €", "92,52 €", "5.148,15 €", "33.885,68 €"],
                ["7 kW", "14", "9.317,00 €", "145,39 €", "107,94 €", "6.188,67 €", "40.067,13 €"],
                ["8 kW", "16", "10.164,00 €", "166,16 €", "117,75 €", "7.902,05 €", "46.921,45 €"],
                ["10 kW", "20", "12.100,00 €", "207,70 €", "140,18 €", "10.992,39 €", "60.293,64 €"],
            ],
            "en": [
                ["5 kW", "10", "€6,957.50", "€103.85", "€80.60", "€3,687.09", "€27,283.69"],
                ["6 kW", "12", "€7,986.00", "€124.62", "€92.52", "€5,148.15", "€33,885.68"],
                ["7 kW", "14", "€9,317.00", "€145.39", "€107.94", "€6,188.67", "€40,067.13"],
                ["8 kW", "16", "€10,164.00", "€166.16", "€117.75", "€7,902.05", "€46,921.45"],
                ["10 kW", "20", "€12,100.00", "€207.70", "€140.18", "€10,992.39", "€60,293.64"],
            ],
        },
    },
    "financiacion_nota_1": {
        "grupo": "financiacion",
        "etiqueta": "Nota legal 1 (precio de la energía)",
        "tipo": "texto",
        "max_length": MAX_TEXTO,
        "defecto": {
            "es": "* Estimación de rentabilidad calculada con un precio de energía de 0,16 €/kWh + IVA.",
            "en": "* Profitability estimate calculated with an energy price of €0.16/kWh + VAT.",
        },
    },
    "financiacion_nota_2": {
        "grupo": "financiacion",
        "etiqueta": "Nota legal 2 (condiciones de financiación)",
        "tipo": "texto",
        "max_length": MAX_TEXTO,
        "defecto": {
            "es": "* Financiación: 100% de la inversión + IVA a 10 años al 6,95% de interés.",
            "en": "* Financing: 100% of the investment + VAT over 10 years at 6.95% interest.",
        },
    },
}

IDIOMAS = ("es", "en")


def campo(clave: str) -> dict | None:
    return CAMPOS.get(clave)


def defecto(clave: str, idioma: str):
    """Valor original del campo, el que estaba escrito en el HTML antes del CMS."""
    definicion = CAMPOS.get(clave)
    if not definicion:
        return None
    return definicion["defecto"].get(idioma)


def validar(clave: str, valor) -> str | None:
    """Devuelve un mensaje de error en castellano, o None si el valor es aceptable.

    Los mensajes los lee directamente el personal de la empresa en el panel, así que van
    sin jerga técnica y diciendo qué hacer para arreglarlo."""
    definicion = CAMPOS.get(clave)
    if not definicion:
        return "Ese campo no existe."

    if definicion["tipo"] == "tabla":
        if not isinstance(valor, list) or not valor:
            return "La tabla necesita al menos una fila."
        if len(valor) > definicion["max_filas"]:
            return f"La tabla admite como máximo {definicion['max_filas']} filas."
        n_columnas = len(definicion["columnas"])
        for fila in valor:
            if not isinstance(fila, list) or len(fila) != n_columnas:
                return f"Cada fila debe tener {n_columnas} celdas."
            for celda in fila:
                if not isinstance(celda, str):
                    return "Las celdas solo pueden contener texto."
                if len(celda) > definicion["max_length"]:
                    return f"Hay una celda demasiado larga (máximo {definicion['max_length']} caracteres)."
        return None

    if not isinstance(valor, str):
        return "El valor debe ser texto."
    if not valor.strip():
        return "Este campo no puede quedarse vacío. Si quieres el texto de antes, usa «Restaurar original»."
    if len(valor) > definicion["max_length"]:
        return (
            f"Te has pasado de largo: {len(valor)} caracteres y el máximo son "
            f"{definicion['max_length']}. Acorta el texto un poco."
        )
    if definicion["tipo"] == "numero" and not valor.strip().isdigit():
        return "Este campo solo admite un número entero, sin puntos ni letras."
    return None
