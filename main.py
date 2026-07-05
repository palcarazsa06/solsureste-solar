import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
import database as db

# Importamos nuestros prompts y esquemas
from agentes.supervisor import PROMPT_SUPERVISOR, DecisionRuta
from agentes.cualificador import PROMPT_CUALIFICADOR
from agentes.agendador import PROMPT_AGENDADOR

# Importamos todas las tools limpias y sin duplicados
from tools.calendar_tools import tool_reservar_cita, reservar_cita
from tools.rag_tools import tool_consultar_dudas, buscar_informacion

# Importamos las guardas de seguridad
from guardrails import verificar_input, verificar_output, MENSAJE_RECHAZO_ES

# para la crm
from tools.crm_tools import tool_enviar_lead, enviar_lead_crm
from database import reset_conversacion

from logging_config import get_logger
logger = get_logger(__name__)

# Cargamos las variables de entorno (.env)
load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=15.0,
)

# Inicializamos la base de datos local
db.init_db()

MENSAJE_DESPEDIDA_ES = "¡Gracias por contactar con nosotros! Que tengas un buen día."

class _DespedidaTraducida(BaseModel):
    idioma_usuario: str = Field(description="Código de idioma (es, en, fr, de, etc.) detectado en el mensaje del cliente.")
    mensaje_traducido: str = Field(description=(
        f"Traducción natural (no literal palabra por palabra), en ese idioma, de esta frase de "
        f"despedida: '{MENSAJE_DESPEDIDA_ES}'."
    ))

async def _generar_despedida(historial) -> tuple[str, int, int]:
    """Traduce el mensaje fijo de despedida al idioma del último mensaje del cliente. Llamada aparte
    y minimalista (no la hace el Supervisor): con el prompt de enrutamiento completo de por medio,
    el modelo no seguía de forma fiable la instrucción de idioma para este campo."""
    ultimo_mensaje_usuario = next(
        (m["content"] for m in reversed(historial) if m.get("role") == "user"), ""
    )
    prompt = f"""Detecta el idioma en el que está escrito este mensaje de un cliente en una conversación
    comercial de chat: "{ultimo_mensaje_usuario}"
    Luego traduce de forma natural (no literal) a ESE MISMO idioma la siguiente frase de despedida:
    "{MENSAJE_DESPEDIDA_ES}\""""

    try:
        respuesta = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format=_DespedidaTraducida,
        )
        parsed = respuesta.choices[0].message.parsed
        usage = respuesta.usage
        return parsed.mensaje_traducido, usage.prompt_tokens, usage.completion_tokens
    except Exception as e:
        logger.warning(f"No se pudo traducir el mensaje de despedida, se usa el fallback en español: {e}")
        return MENSAJE_DESPEDIDA_ES, 0, 0

def recortar_historial(historial, max_mensajes=12):
    """
    Se queda con los últimos 'max_mensajes', pero asegura de no cortar
    a medias una llamada a herramienta (tool_call) para evitar que la API falle.
    """
    if len(historial) <= max_mensajes:
        return historial

    indice_corte = len(historial) - max_mensajes

    while indice_corte > 0:
        primer_mensaje_del_recorte = historial[indice_corte]

        if primer_mensaje_del_recorte.get("role") == "tool" or \
           (primer_mensaje_del_recorte.get("role") == "assistant" and "tool_calls" in primer_mensaje_del_recorte):
            indice_corte -= 1
        else:
            break

    return historial[indice_corte:]

def _construir_contexto_agente(siguiente_agente):
    """Devuelve (prompt_especialista, herramientas_activas) según el agente elegido por el
    Supervisor. Aislamiento de herramientas por agente: CUALIFICADOR solo buscar_informacion
    + enviar_lead_crm, AGENDADOR solo reservar_cita — no mezclar."""
    if siguiente_agente == "CUALIFICADOR":
        return PROMPT_CUALIFICADOR, [tool_consultar_dudas, tool_enviar_lead]

    # AGENDADOR
    hoy = datetime.now()
    dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    dia_nombre = dias_semana[hoy.weekday()]
    fecha_actual_contexto = f"{hoy.strftime('%Y-%m-%d')} (hoy es {dia_nombre})"

    # Tabla de los próximos 14 días ya calculada por Python: el modelo NO debe hacer
    # aritmética de fechas de cabeza (se comprobó que gpt-4o-mini falla calculando
    # "el día de la semana X" a partir de la fecha de hoy — solo debe copiar de esta tabla).
    tabla_fechas = "\n".join(
        f"        - {(hoy + timedelta(days=i)).strftime('%Y-%m-%d')} → {dias_semana[(hoy + timedelta(days=i)).weekday()]}"
        + (" (hoy)" if i == 0 else " (mañana)" if i == 1 else "")
        for i in range(14)
    )

    prompt_especialista = PROMPT_AGENDADOR + f"""

        CONTEXTO TEMPORAL CRÍTICO:
        - La fecha real de HOY es: {fecha_actual_contexto}.
        - PROHIBIDO calcular de cabeza qué fecha corresponde a un día de la semana. Usa EXCLUSIVAMENTE
          esta tabla ya calculada de los próximos 14 días para traducir lo que diga el usuario
          ('mañana', 'el jueves', 'la semana que viene', etc.) a una fecha YYYY-MM-DD exacta:
{tabla_fechas}
        - Si el usuario dice un día de la semana sin más (ej. "el jueves") y hoy todavía no ha pasado
          ese día en esta semana, usa la PRIMERA fecha de la tabla que coincida con ese día de la
          semana (el más próximo). Si dice "el jueves que viene" o "la semana que viene", usa la
          segunda ocurrencia de ese día en la tabla.
        - Una vez identificada la fecha exacta en la tabla, DEBES ejecutar obligatoriamente la
          herramienta 'reservar_cita' con esa fecha. No te limites a confirmar con texto.
        """
    return prompt_especialista, [tool_reservar_cita]

async def _extraer_y_guardar_lead(user_id, historial_para_ia) -> tuple[int, int]:
    """Extrae los datos de contacto del historial vía LLM, los guarda en SQLite, envía el
    lead al CRM (con guard anti-duplicado) y dispara la alerta por email. Devuelve
    (tok_prompt, tok_completion) de las llamadas hechas aquí."""
    tok_prompt = 0
    tok_completion = 0
    logger.info("Extrayendo datos del historial para la Base de Datos...")

    prompt_extraccion = """Analiza el siguiente historial de conversación y extrae los datos del cliente.
    Devuelve ÚNICAMENTE un objeto JSON válido con estas claves exactas:
    {"nombre": "...", "correo": "...", "telefono": "...", "ciudad": "..."}
    Si algún dato falta, pon "Desconocido". No devuelvas ningún otro texto, solo el JSON puro.
    """

    mensajes_extraccion = [{"role": "system", "content": prompt_extraccion}] + historial_para_ia

    try:
        respuesta_extraccion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=mensajes_extraccion,
            response_format={"type": "json_object"}
        )
        tok_prompt += respuesta_extraccion.usage.prompt_tokens
        tok_completion += respuesta_extraccion.usage.completion_tokens

        datos_extraidos = json.loads(respuesta_extraccion.choices[0].message.content)

        nombre_limpio = datos_extraidos.get("nombre", "Desconocido")
        correo_limpio = datos_extraidos.get("correo", "Desconocido")
        telefono_limpio = datos_extraidos.get("telefono", "Desconocido")
        ciudad_limpia = datos_extraidos.get("ciudad", "Desconocido")

        db.update_datos_cliente(user_id, nombre_limpio, correo_limpio, telefono_limpio, ciudad_limpia)
        logger.info(f"Datos guardados en SQLite: {nombre_limpio} | {telefono_limpio} | {correo_limpio}")

        if not db.crm_ya_enviado(user_id):
            try:
                await enviar_lead_crm(nombre=nombre_limpio, telefono=telefono_limpio, ubicacion=ciudad_limpia, necesidad="Instalación Solar")
                db.marcar_crm_enviado(user_id)
            except Exception as error_crm:
                logger.warning(f"Se guardó en la DB pero falló el envío al CRM externo: {error_crm}")
        else:
            logger.info("CRM ya enviado previamente para este usuario, se omite el duplicado.")

        # Alerta email al propietario (fire-and-forget). Independiente del envío al CRM:
        # el CUALIFICADOR puede haber enviado ya el lead al CRM en un turno anterior
        # (vía su propia herramienta 'enviar_lead_crm'), pero eso no debe impedir que
        # llegue el aviso por email cuando la cita se agenda de verdad. El guard del llamador
        # (estado_actual != "AGENDADOR") ya garantiza que esto solo se ejecute una vez.
        try:
            from tools.email_tools import enviar_alerta_lead_email
            asyncio.create_task(enviar_alerta_lead_email(
                nombre=nombre_limpio, telefono=telefono_limpio,
                correo=correo_limpio, ciudad=ciudad_limpia, fuente="chat"
            ))
        except Exception as e_email:
            logger.warning(f"No se pudo lanzar la alerta email: {e_email}")

    except Exception as e:
        logger.error(f"Error al extraer JSON para la Base de Datos: {e}", exc_info=True)

    return tok_prompt, tok_completion

async def _handler_reservar_cita(args, user_id):
    return await reservar_cita(
        fecha=args.get("fecha"),
        hora=args.get("hora"),
        nombre=args.get("nombre", "Cliente"),
        telefono=args.get("telefono", "Sin teléfono"),
        ciudad=args.get("ciudad", "Desconocida")
    )

async def _handler_buscar_informacion(args, user_id):
    return await buscar_informacion(args["pregunta"])

async def _handler_enviar_lead_crm(args, user_id):
    if not db.crm_ya_enviado(user_id):
        resultado = await enviar_lead_crm(args["nombre"], args["telefono"], args["ubicacion"], args["necesidad"])
        db.marcar_crm_enviado(user_id)
        return resultado
    logger.info("CRM ya enviado previamente para este usuario, se omite el duplicado.")
    return json.dumps({"status": "skipped", "mensaje": "Lead ya enviado al CRM anteriormente."})

# Aislamiento de herramientas por agente ya garantizado por _construir_contexto_agente
# (qué tools se ofrecen al LLM); este registry solo despacha la ejecución cuando el LLM
# decide llamarlas.
MANEJADORES_HERRAMIENTAS = {
    "reservar_cita": _handler_reservar_cita,
    "buscar_informacion": _handler_buscar_informacion,
    "enviar_lead_crm": _handler_enviar_lead_crm,
}

async def procesar_mensaje(user_id, mensaje_usuario):
    """El cerebro del sistema: enruta el mensaje y devuelve la respuesta del especialista usando sus propias herramientas."""

    # Acumulador de tokens para esta request
    tok_prompt = 0
    tok_completion = 0

    # 0. Si el usuario vuelve a escribir tras haber terminado, reiniciamos la sesión
    estado_previo, _ = db.get_conversacion(user_id)
    if estado_previo == "TERMINAR":
        reset_conversacion(user_id)

    # 1. Recuperamos el historial ANTES de evaluar para darle contexto al firewall
    _, historial_completo = db.get_conversacion(user_id)
    historial_reciente = recortar_historial(historial_completo, max_mensajes=12)

    # --- 🛡️ 2. INPUT GUARDRAIL ---
    es_valido, mensaje_rechazo, p, c = await verificar_input(mensaje_usuario, historial_reciente)
    tok_prompt += p
    tok_completion += c

    if not es_valido:
        db.acumular_tokens(user_id, tok_prompt, tok_completion)
        return mensaje_rechazo or MENSAJE_RECHAZO_ES

    # 3. Si pasa el filtro, guardamos el mensaje nuevo en la BD
    db.append_mensaje(user_id, "user", mensaje_usuario)

    # Volvemos a leer y recortar para incluir el mensaje del usuario que acabamos de añadir
    _, historial_actualizado = db.get_conversacion(user_id)
    historial_para_ia = recortar_historial(historial_actualizado, max_mensajes=12)

    # 4. EL SUPERVISOR DECIDE
    mensajes_supervisor = [{"role": "system", "content": PROMPT_SUPERVISOR}] + historial_para_ia

    respuesta_sup = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=mensajes_supervisor,
        response_format=DecisionRuta,
    )
    decision = respuesta_sup.choices[0].message.parsed
    siguiente_agente = decision.siguiente_agente
    tok_prompt += respuesta_sup.usage.prompt_tokens
    tok_completion += respuesta_sup.usage.completion_tokens

    logger.info(f"Supervisor decide pasar a: {siguiente_agente} | Motivo: {decision.razonamiento}")

    # Si el Supervisor decide que ya es hora de pasar al Agendador, disparamos
    # la extracción de datos y el envío al CRM.
    if siguiente_agente == "AGENDADOR":
        estado_actual, _ = db.get_conversacion(user_id)
        if estado_actual != "AGENDADOR":
            p, c = await _extraer_y_guardar_lead(user_id, historial_para_ia)
            tok_prompt += p
            tok_completion += c

    if siguiente_agente == "TERMINAR":
        mensaje_despedida, p, c = await _generar_despedida(historial_para_ia)
        tok_prompt += p
        tok_completion += c
        db.update_estado(user_id, "TERMINAR")
        db.acumular_tokens(user_id, tok_prompt, tok_completion)
        return mensaje_despedida

    # 5. PREPARAMOS AL ESPECIALISTA Y SUS HERRAMIENTAS DINÁMICAMENTE
    prompt_especialista, herramientas_activas = _construir_contexto_agente(siguiente_agente)

    mensajes_agente = [{"role": "system", "content": prompt_especialista}] + historial_para_ia

    respuesta_agente = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=mensajes_agente,
        tools=herramientas_activas,
        temperature=0.3
    )

    mensaje_ia = respuesta_agente.choices[0].message
    tok_prompt += respuesta_agente.usage.prompt_tokens
    tok_completion += respuesta_agente.usage.completion_tokens

    # 6. COMPROBAMOS SI LA IA HA DECIDIDO USAR UNA HERRAMIENTA
    if mensaje_ia.tool_calls:
        # A) Guardamos la petición de la IA (tool_call) en la DB
        db.append_mensaje_dict(user_id, mensaje_ia.model_dump(exclude_unset=True))

        # B) Ejecutamos la función de Python correspondiente
        for tool_call in mensaje_ia.tool_calls:
            args = json.loads(tool_call.function.arguments)
            handler = MANEJADORES_HERRAMIENTAS.get(tool_call.function.name)
            resultado_python = (
                await handler(args, user_id) if handler
                else json.dumps({"error": "Herramienta desconocida"})
            )

            # C) Guardamos el resultado en la DB con rol "tool"
            mensaje_resultado = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": resultado_python
            }
            db.append_mensaje_dict(user_id, mensaje_resultado)

        # D) Volvemos a llamar a la IA para que lea el resultado de la DB y responda
        _, historial_final = db.get_conversacion(user_id)
        historial_para_ia_final = recortar_historial(historial_final, max_mensajes=12)

        mensajes_agente_final = [{"role": "system", "content": prompt_especialista}] + historial_para_ia_final

        respuesta_final_agente = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=mensajes_agente_final,
            temperature=0.3
        )
        respuesta_final = respuesta_final_agente.choices[0].message.content
        tok_prompt += respuesta_final_agente.usage.prompt_tokens
        tok_completion += respuesta_final_agente.usage.completion_tokens

    else:
        respuesta_final = mensaje_ia.content

    # --- 🛡️ 7. OUTPUT GUARDRAIL ANTES DE GUARDAR ---
    respuesta_final_segura, p, c = await verificar_output(respuesta_final)
    tok_prompt += p
    tok_completion += c

    db.append_mensaje(user_id, "assistant", respuesta_final_segura)

    # 8. Actualizamos la fase en la que se quedó el usuario
    db.update_estado(user_id, siguiente_agente)

    # 9. Guardamos el coste acumulado de esta request
    db.acumular_tokens(user_id, tok_prompt, tok_completion)
    logger.info(f"[TOKENS] Request de {user_id}: {tok_prompt} prompt + {tok_completion} completion = {tok_prompt + tok_completion} total")

    return respuesta_final_segura

# ---------------------------------------------------------
# BUCLE DE CHAT EN TERMINAL PARA PRUEBAS
# ---------------------------------------------------------
if __name__ == "__main__":
    async def _chat_loop():
        print("🤖 Sistema Multi-Agente iniciado. Escribe 'salir' para terminar.")
        usuario_demo = "cliente_whatsapp_001"

        while True:
            mensaje = input("\nTú: ")
            if mensaje.lower() in ['salir', 'exit', 'quit']:
                print("Cerrando sistema...")
                break

            respuesta = await procesar_mensaje(usuario_demo, mensaje)
            print(f"Agente: {respuesta}")

    asyncio.run(_chat_loop())
