# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

Landing page + motor de ventas conversacional para **Solsureste Solar** (instalación de placas
solares y huertos solares en Murcia y Alicante). Arquitectura multi-agente con router supervisor,
RAG con ChromaDB, integración con Google Calendar y webhook CRM. Desplegado en Render, dominio de
producción `solsurestesolar.com`.

El repo empezó como una landing estática (frontend puro, sin backend) y se integró con un motor de
ventas real portado de otro proyecto (`mi_agencia_ia`). El frontend (antes en la raíz) ahora vive en
`static/` y se sirve desde FastAPI junto con la API.

## Stack

- **Backend**: FastAPI + Uvicorn
- **LLM**: OpenAI GPT-4o-mini (structured output con Pydantic para decisiones de routing/guardrails)
- **Vector store**: ChromaDB (persistente en disco) para RAG
- **Base de datos**: SQLite (`agencia.db`) para historial de conversaciones y leads
- **Integraciones**: Google Calendar API (service account), webhook CRM (Make.com → Google Sheets),
  alertas por email (Gmail SMTP)
- **Frontend**: HTML/CSS/JS estático en `static/` (sin build step, sin framework)
- **Hosting**: Render (Web Service con disco persistente)

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # rellenar OPENAI_API_KEY, ADMIN_USER/PASSWORD, CRM_WEBHOOK_URL, etc.
```

`credenciales_google.json` (service account de Google Calendar) debe existir en la raíz del proyecto
(o en `$DATA_DIR`, ver más abajo) — está en `.gitignore`, nunca se commitea.

## Comandos

```bash
python api.py                                  # servidor dev en localhost:8000, reload=True
uvicorn api:app --host 0.0.0.0 --port $PORT     # arranque de producción (el que usa Render), sin reload
python main.py                                  # chatbot en terminal, sin servidor HTTP, para explorar el flujo libremente
python cargar_pdfs.py                           # (re)indexa /documentos en ChromaDB — ejecutar tras editar la base de conocimiento
python ver_bd.py                                # resumen rápido de leads en agencia.db (user_id, estado, últimos mensajes)
./test_conversacion.sh                          # única suite de regresión — requiere jq y el servidor ya corriendo en localhost:8000
tail -f logs/agencia.log                        # logs en vivo (o $DATA_DIR/logs/agencia.log en producción)
```

**No hay framework de tests unitarios (sin pytest).** `test_conversacion.sh` es la única red de
regresión automatizada: cubre flujo de cualificación (5 turnos), guardrail off-topic, guardrail de
inyección de prompt, endpoint `/presupuesto`, sesión inválida (401) y rate limit (429). Lee las
credenciales admin del `.env` para limpiar los usuarios de prueba que crea. Para probar un escenario
suelto o nuevo, seguir el mismo patrón manualmente: `POST /session` → `POST /chat` reusando el mismo
`user_id` en turnos sucesivos (ver el propio script como plantilla), leyendo `logs/agencia.log` para
ver la decisión real del supervisor y los argumentos exactos pasados a las tools.

## Arquitectura: Sistema Router Multi-Agente

```
Mensaje de usuario
    ↓
[INPUT GUARDRAIL] (guardrails.py) → bloquea spam/OOT antes de cualquier lógica
    ↓
[SUPERVISOR] (main.py / agentes/supervisor.py) — GPT-4o-mini structured output → DecisionRuta
  ├─ CUALIFICADOR — preguntas, recopilación de datos (90% del tráfico)
  ├─ AGENDADOR   — solo cuando hay 4 datos + fecha/hora confirmados
  └─ TERMINAR    — finalizar conversación
    ↓
[ESPECIALISTA] ejecuta con herramientas propias (aisladas por agente)
    ↓
[OUTPUT GUARDRAIL] (guardrails.py) → corrige formato/alucinaciones antes de almacenar y devolver
```

**Regla crítica del supervisor**: AGENDADOR solo se activa cuando los 4 campos (nombre, teléfono,
correo, ciudad) están explícitamente en el historial Y el usuario ha dado fecha+hora concretas. Si
solo dice "sí" o "vale", va al CUALIFICADOR. `DecisionRuta.siguiente_agente` es un `str` plano, no un
enum — no está forzado a nivel de esquema, solo por prompt.

## Archivos clave

- `main.py` — `procesar_mensaje()`: orquesta todo el flujo. Contiene `recortar_historial()` (recorta a
  12 mensajes sin partir un `tool_call`/resultado a medias), la extracción JSON de datos de contacto
  al entrar en AGENDADOR, y el bloque `CONTEXTO TEMPORAL CRÍTICO` que se inyecta solo en el prompt del
  Agendador con una **tabla precalculada de los próximos 14 días** (nombre de día → fecha exacta) — no
  se le pide al modelo que calcule fechas relativas de cabeza porque se demostró que gpt-4o-mini falla
  calculando qué día de la semana corresponde a una fecha (ver "Detalles importantes").
- `api.py` — FastAPI: `/session`, `/chat`, `/presupuesto`, `/api/leads` (admin-only), `/admin`, `/faq`,
  `/aviso-legal`, `/privacidad`, `/cookies` (páginas estáticas servidas vía `FileResponse`, mismo
  patrón que `/admin`), sirve `static/` como fallback. Rate limit en memoria (20 req/60s por IP) en
  `/chat`, `/presupuesto` y los tres endpoints `/api/leads/*`. Sesiones HMAC firmadas, security
  headers, validación de inputs, `GZipMiddleware` y `Cache-Control` para estáticos (`/images/`,
  `/videos/`, `/icon-*`, `.css`, `.js`).
- `agentes/supervisor.py` — prompt de enrutamiento + schema Pydantic `DecisionRuta`.
- `agentes/cualificador.py` — agente de ventas con RAG obligatorio (`buscar_informacion`) y acceso a
  `enviar_lead_crm`. Su sección de "protocolo de seguridad" solo debe activarse ante intentos reales
  de romper sus instrucciones — no ante saludos genéricos ni peticiones de datos de contacto públicos
  de la empresa (teléfono/email/dirección), fue una fuente real de falsos positivos.
- `agentes/agendador.py` — prompt de cierre de cita. No tiene estado propio; `main.py` le concatena el
  bloque temporal en tiempo de ejecución.
- `tools/rag_tools.py` — `buscar_informacion()`: embeddings con `text-embedding-3-small`, top-3 en la
  colección `conocimiento_empresa`, filtra por distancia L2 ≤ 1.2. Caché en memoria por pregunta
  normalizada (se vacía al reiniciar el proceso). El cliente de ChromaDB se crea **en el momento del
  import**, no de forma perezosa.
- `tools/calendar_tools.py` — `reservar_cita()`: service account desde `credenciales_google.json`,
  `GOOGLE_CALENDAR_ID` del `.env` (fallback hardcodeado). Espera `fecha` en `YYYY-MM-DD` y `hora` en
  `HH:MM` exactos; cualquier otro formato revienta el `strptime` (capturado, devuelve error genérico).
- `tools/crm_tools.py` — `enviar_lead_crm()`: POST a `CRM_WEBHOOK_URL` (actualmente un escenario de
  Make.com que escribe en una Google Sheet). Si no está configurado, solo loguea un warning.
- `tools/email_tools.py` — `enviar_alerta_lead_email()`: alerta por Gmail SMTP (puerto 587,
  STARTTLS). Se dispara fire-and-forget vía `asyncio.create_task` desde `main.py` (flujo de chat) y
  `api.py` (`/presupuesto`). Es una notificación **independiente** del envío al CRM — no debe quedar
  anidada dentro del mismo guard de "CRM ya enviado" (ver "Detalles importantes").
- `guardrails.py` — `verificar_input`: firewall de entrada (bloquea off-topic/ataques, con reglas
  explícitas para no bloquear preguntas legítimas de negocio aunque suenen genéricas). `verificar_output`:
  revisa/corrige la respuesta antes de guardarla, con un fast-path regex (`_es_claramente_segura`) que
  evita la llamada al LLM para respuestas obviamente limpias.
- `database.py` — SQLite en modo WAL. Tabla `conversaciones` (estado, historial JSON, datos de
  contacto, coste acumulado, flag `gestionado`). Tabla `stats` con `coste_historico` (se alimenta del
  coste de conversaciones eliminadas, para no perder la cuenta al borrar leads desde el admin).
  `reset_conversacion()` limpia historial y datos de contacto pero **no** el coste acumulado ni
  `gestionado` — persisten a través de un reset.
- `static/admin.html` — panel de administración (login propio + Basic Auth a nivel de servidor en
  `/admin`, doble capa). Tabla de leads con filtros por texto (insensible a tildes) y por estado,
  marcar gestionado, eliminar, coste total acumulado.
- `static/script.js` — además de la UI (chat, formulario, contadores, reveals, tarjetas spotlight),
  `setupStory()` monta un canvas WebGL fijo a pantalla completa (`#sss-story`, detrás de todo el
  contenido) que dibuja un shader de 7 actos (`ACTO I` sol → `ACTO VII` amanecer) controlado por el
  progreso de scroll de **toda la página** (`scrollTop / (scrollHeight - clientHeight)`, suavizado con
  lerp). El "sol" que se ve en el hero no es un asset del hero — es este canvas de fondo asomando a
  través de los overlays semitransparentes de `#inicio` (ver gotcha en "Detalles importantes").
- `documentos/solsureste_base_conocimiento.txt` — fuente de verdad del RAG. Tras editarlo, ejecutar
  `python cargar_pdfs.py` y **reiniciar el proceso del servidor** (ver gotcha de ChromaDB abajo).
- `test_conversacion.sh` — regresión end-to-end vía curl+jq contra un servidor ya corriendo.
- `static/faq.html` — página `/faq` con las 9 preguntas frecuentes reales (acordeón `<details>`),
  schema `FAQPage` + `BreadcrumbList`. Autocontenida (su propio `<style>`, sin depender de
  `styles.css`). Si se edita el contenido, mantener el texto sincronizado con la sección "FAQ" de
  `documentos/solsureste_base_conocimiento.txt` y con el JSON-LD de `static/index.html`.
- `static/aviso-legal.html`, `static/privacidad.html`, `static/cookies.html` — páginas legales
  (rutas `/aviso-legal`, `/privacidad`, `/cookies`), mismo patrón autocontenido que `faq.html`. El
  contenido de `privacidad.html` describe los tratamientos reales (RAG en `agencia.db`, Google
  Calendar, CRM, email de alerta, GA4) — si se añade una integración nueva que trate datos
  personales, actualizar esta página también.
- `static/consent.js` — banner de consentimiento de cookies; solo carga `gtag.js` (GA4, ID
  `G-X15TLEX3MB`) tras aceptación explícita, guardada en `localStorage['sss_cookie_consent']`.
  Incluido en todas las páginas públicas (`index.html`, `faq.html`, y las 3 legales).
- `static/manifest.json` — manifest PWA mínimo (iconos `icon-192.png`/`icon-512.png` generados desde
  `static/images/logo.jpg`).
- `documentos/plantilla-pagina-seo.html` — plantilla comentada usada como base para las páginas de
  ciudad/provincia de abajo. Vive fuera de `static/` a propósito para que `StaticFiles` nunca la sirva
  por accidente. Sigue sirviendo de base para futuras páginas de servicio (residencial/industrial/
  huertos solares/mantenimiento), aún no implementadas.
- `static/placas-solares-{murcia,alicante}.html` — páginas **pilar** de SEO local (rutas
  `/placas-solares-murcia` y `/placas-solares-alicante`), cobertura a nivel provincia/región. Enlazan
  a sus páginas de ciudad correspondientes vía `.cluster-links`. Schema `Service` (no `LocalBusiness`
  duplicado) con `areaServed` de tipo `AdministrativeArea`.
- `static/placas-solares-{lorca,cartagena,molina-de-segura,orihuela,torrevieja,orihuela-costa,
  pilar-de-la-horadada}.html` — páginas **clúster** de ciudad/comarca (modelo pilar→clúster, ver
  "Detalles importantes"). Cada una enlaza de vuelta a su pilar vía breadcrumb + enlace inline.
  Lorca/Cartagena/Orihuela expanden los casos reales que también aparecen (de forma resumida, con
  teaser "Leer caso completo →") en la sección "Resultados reales" de `static/index.html`. Schema
  `Service` con `areaServed` de tipo `City`.

## DATA_DIR — persistencia en producción (Render)

`agencia.db`, `chroma_db/`, `logs/` y `credenciales_google.json` resuelven su ruta a partir de la
variable de entorno `DATA_DIR` (por defecto `.`, idéntico al comportamiento previo en local). En
Render, `DATA_DIR` apunta al disco persistente montado (p. ej. `/data`), para que esos datos
sobrevivan a redeploys. El `credenciales_google.json` de producción se sube manualmente vía el Shell
de Render (no se puede commitear); `cargar_pdfs.py` debe ejecutarse ahí también tras cada cambio a la
base de conocimiento.

## Detalles importantes

- **ChromaDB y procesos separados — gotcha real y ya nos mordió**: el cliente de ChromaDB se crea al
  importar `tools/rag_tools.py`, en el proceso del servidor web. Si se ejecuta `cargar_pdfs.py` como
  un proceso aparte (p. ej. desde el Shell de Render) mientras el servidor web ya está corriendo, el
  servidor **no ve los datos nuevos** hasta que se reinicia — falla con `Error creating hnsw segment
  reader: Nothing found on disk` o simplemente no encuentra resultados. Regla: tras `cargar_pdfs.py`,
  reiniciar siempre el proceso del servidor (local o en Render).
- **Falsos positivos del guardrail de entrada son comunes y no siempre deterministas**: gpt-4o-mini a
  veces bloquea preguntas de negocio legítimas (zonas no cubiertas, preguntas técnicas sin la palabra
  "placas", propuestas de hora de llamada, despedidas). Al tocar `guardrails.py`, probar cada regla
  nueva con 3-5 repeticiones antes de darla por buena — un solo intento no es suficiente evidencia.
- **Alucinaciones de cifras no cubiertas por el guardrail de salida**: el guardrail de salida original
  solo comprobaba precios/marcas/plazos/financiación inventados; no cubría **garantías** (el modelo
  llegó a inventar "25 años de garantía" sin que el guardrail lo detectara). Al añadir nuevas
  categorías de datos de negocio, recordar añadirlas también a `EvaluacionOutput` en `guardrails.py`.
- **No pedir al modelo que calcule fechas relativas de cabeza**: se comprobó que gpt-4o-mini calcula
  mal qué fecha corresponde a "el jueves" dado el día de hoy. `main.py` inyecta una tabla ya calculada
  de los próximos 14 días en el prompt del Agendador — no revertir a "calcula matemáticamente".
- **Doble envío al CRM**: el lead puede enviarse al CRM desde dos sitios — el CUALIFICADOR con su
  propia herramienta `enviar_lead_crm` (en cuanto confirma los 4 datos) o el bloque de transición a
  AGENDADOR en `main.py`. Ambos comprueban `db.crm_ya_enviado()` para no duplicar. El envío de email
  de alerta es una notificación aparte y debe dispararse siempre que se llega a AGENDADOR por primera
  vez, **independientemente** de si el CRM ya se había enviado antes desde el CUALIFICADOR.
- **Auto-reset al volver tras TERMINAR**: si un usuario en estado `TERMINAR` escribe de nuevo,
  `procesar_mensaje` llama a `reset_conversacion` antes de continuar (borra historial y contacto, pero
  no el coste acumulado).
- **Aislamiento de herramientas por agente**: CUALIFICADOR tiene `buscar_informacion` + `enviar_lead_crm`;
  AGENDADOR solo `reservar_cita`. No mezclar.
- **Reload local y logging**: `logging_config.py` silencia explícitamente el logger `watchfiles` — sin
  eso, correr `python api.py` (con `reload=True`) crea un bucle infinito, porque cada línea de log
  escrita en `logs/` (dentro del directorio vigilado) dispara una nueva detección de cambio. No quitar
  esa línea.
- **Sesiones HMAC**: `POST /session` → `{uuid}.{hmac_sha256[:16]}`. Si `SECRET_KEY` no está en `.env`,
  se acepta cualquier token (modo dev). El frontend llama a `/session` automáticamente si no hay token
  guardado.
- **`.github/workflows/pages.yml` eliminado**: desplegaba el repo entero a GitHub Pages en cada push a
  `main`, residuo de cuando este repo era solo la landing estática sin backend. Se eliminó porque
  podía indexar una copia duplicada/rota del sitio en una URL `.github.io`. Si GitHub Pages seguía
  activo en la configuración del repo (Settings → Pages) antes de este cambio, desactivarlo también
  ahí manualmente.
- **`robots.txt`** bloquea `/admin`, `/api/`, `/session` y `/presupuesto` de los crawlers. `/faq`,
  `/aviso-legal`, `/privacidad` y `/cookies` sí son crawleables (están en `sitemap.xml`).
- **El hero debe quedarse semitransparente, nunca opaco**: dentro de `#inicio`, las capas
  `.sss-hero-bg-cinematic`/`.sss-hero-bg-aurora` solo deben llevar overlays semitransparentes
  (degradados, blur) — cualquier capa opaca ahí (un `<video>` de fondo, un `background` sólido) tapa
  por completo el canvas `#sss-story` que pinta el sol/rayos/partículas del Acto I, aunque el canvas
  siga renderizando con normalidad por debajo. Ya pasó una vez: un `<video>` de dron sin commitear
  ocultó el sol durante una sesión entera hasta rastrear la causa real.
- **NAP (nombre/dirección/teléfono) unificado**: la dirección real es **Calle Aldebarán, 51, P.I. La
  Estrella, Molina de Segura (30509), Murcia** — tel. 968 869 532, info@solsurestesolar.com. Este dato
  ya coincidía en el HTML pero `documentos/solsureste_base_conocimiento.txt` tenía una dirección
  antigua distinta ("Calle Alarilla, 3, Bajo — 30002 Murcia"), lo que hacía que el chatbot diera una
  dirección incorrecta a clientes reales. Ya está corregido en el RAG (y reindexado). Si se vuelve a
  editar el NAP, actualizar a la vez: `documentos/solsureste_base_conocimiento.txt` (tras editar,
  `cargar_pdfs.py` + reiniciar servidor), el JSON-LD `HomeAndConstructionBusiness` en
  `static/index.html`, y las 3 páginas legales.
- **Modelo pilar→clúster para SEO local**: las 9 páginas `static/placas-solares-*.html` siguen un
  esquema de 2 niveles — `/placas-solares-murcia` y `/placas-solares-alicante` son páginas **pilar**
  (cobertura a nivel región/provincia) que enlazan a sus páginas de ciudad; cada página de ciudad
  enlaza de vuelta a su pilar (breadcrumb + enlace inline). Al añadir una ciudad nueva: crear la
  página, enlazarla desde su pilar (`.cluster-links`), añadirla a `static/sitemap.xml` y registrarla
  en `api.py` con el mismo patrón `@app.get("/placas-solares-<slug>")`.
- **Orihuela vs. Orihuela Costa no es contenido duplicado**: son la misma entidad municipal pero dos
  ángulos de negocio deliberadamente distintos — `/placas-solares-orihuela` cubre la vega
  agrícola/interior (huertos solares, bombeo de riego), `/placas-solares-orihuela-costa` cubre las
  urbanizaciones de la franja litoral (Campoamor, Cabo Roig, La Zenia, Playa Flamenca, Villamartín,
  Dehesa de Campoamor), con perfil de cliente y consumo completamente distinto. Cada página enlaza
  explícitamente a la otra en un aviso al inicio del contenido para evitar confusión al usuario y a
  Google. Por el mismo motivo de evitar "doorway pages", **no** se creó una URL propia para Torre de
  la Horadada (es una sección dentro de `/placas-solares-pilar-de-la-horadada`) ni para las
  urbanizaciones individuales de Orihuela Costa — son secciones dentro de esa misma página, no rutas
  independientes.
