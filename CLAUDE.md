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
pytest -q                                       # tests unitarios (recorte de historial, sesiones HMAC, fast-path de guardrails)
pytest tests/test_main.py::test_recortar_historial_no_parte_un_tool_call_a_medias   # un solo test
pytest --cov=. --cov-report=term-missing        # cobertura real (ver huecos conocidos más abajo)
./test_conversacion.sh                          # regresión end-to-end vía curl+jq, requiere el servidor ya corriendo en localhost:8000
tail -f logs/agencia.log                        # logs en vivo (o $DATA_DIR/logs/agencia.log en producción)
```

`pytest`, `pytest-asyncio`, `pytest-socket` y `pytest-cov` no están en `requirements.txt`, viven en
`requirements-dev.txt` (`pip install -r requirements-dev.txt`, también usado por CI). `pytest.ini` fija
`--disable-socket --allow-unix-socket`: cualquier test que intente abrir una conexión de red real (p.
ej. a la API de OpenAI) falla en vez de colgarse — los tests mockean esas llamadas, no las ejecutan.
`tests/conftest.py` define variables de entorno dummy (`OPENAI_API_KEY`, `SECRET_KEY`, etc.) y un
`DATA_DIR` temporal *antes* de que ningún test importe `main`/`api`/`database`/`guardrails`, porque
esos módulos construyen clientes reales (OpenAI, ChromaDB) en el momento del import. Corre en cada
push/PR vía `.github/workflows/tests.yml`, sin necesidad de configurar ningún secret en GitHub.

`tests/test_chat_flow.py` cubre vía `TestClient` + mocks los mismos escenarios que `test_conversacion.sh`
(flujo de cualificación multi-turno, guardrail de entrada, sesión inválida, rate limit) para que corran
en CI sin gastar dinero real en OpenAI ni depender de contenido no determinista del LLM.
`test_conversacion.sh` sigue siendo la única regresión end-to-end **real** (contra un servidor vivo y la
API de OpenAI de verdad): cubre flujo de cualificación (5 turnos), guardrail off-topic, guardrail de
inyección de prompt, endpoint `/presupuesto`, sesión inválida (401) y rate limit (429). Lee las
credenciales admin del `.env` para limpiar los usuarios de prueba que crea. **Importante**:
`CRM_WEBHOOK_URL` en `.env` apunta al escenario REAL de Make.com (no un endpoint de pruebas pese a lo
que decía un comentario antiguo en `crm_tools.py`, ya corregido) — si el flujo de prueba llega a dar
los 4 datos de contacto, crea un lead real en la Google Sheet de clientes; confirmar esto antes de
ejecutar el script si no se está seguro del entorno. Para probar un escenario suelto o nuevo, seguir
el mismo patrón manualmente: `POST /session` → `POST /chat` reusando el mismo `user_id` en turnos
sucesivos (ver el propio script como plantilla), leyendo `logs/agencia.log` para ver la decisión real
del supervisor y los argumentos exactos pasados a las tools.

**Huecos de cobertura conocidos** (medidos con `pytest --cov`, ~81% total): `tools/calendar_tools.py`
(~46%, la llamada real a la API de Google Calendar en `reservar_cita`/`_reservar_cita_sync` no está
testeada más allá de la lógica de horario laboral) y `tools/rag_tools.py` (~50%, el camino real de
embeddings+ChromaDB en `buscar_informacion` no está testeado, solo la lógica de caché). `cargar_pdfs.py`
y `ver_bd.py` están al 0% a propósito — son scripts manuales de un solo uso, no parte del servidor.
No se exige cerrar estos huecos ahora; revisar si crecen mucho al tocar esos archivos.

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
  `/videos/`, `/icon-*`, `.css`, `.js`). **El rate limit es un contador por proceso** (`defaultdict`
  en memoria, `api.py:134`), correcto solo mientras Render corra 1 worker/instancia (hoy es así: el
  arranque de producción no lleva `--workers`). Si algún día se escala horizontalmente, cada proceso
  llevaría su propio contador y el límite total se multiplicaría sin control — requeriría migrar a
  un backend compartido (Redis) para seguir siendo un límite global real. **`/api/leads` devuelve
  todos los leads sin paginación, historial completo incluido** (`database.py:get_all_conversaciones`)
  — evaluado y pospuesto a propósito: `admin.js` ya pinta ese `historial` en línea en la tabla
  ("Historial de Conversación"), así que separarlo en un endpoint bajo demanda rompería esa vista
  salvo que se reescriba también el frontend. Con el volumen real actual (~86 leads) el payload es
  trivial — revisar esto si el número de leads crece mucho. **Redirect de URLs `.html` duplicadas**:
  justo antes del `app.mount(StaticFiles(...))` final, un catch-all `@app.get("/{nombre_pagina}.html")`
  (más una ruta explícita para `/en/index.html`) redirige con 301 a la ruta limpia correspondiente.
  Es necesario porque `StaticFiles(html=True)` sigue sirviendo cualquier archivo por su nombre literal
  con extensión en paralelo a la ruta limpia ya registrada (p. ej. `/placas-solares-murcia.html`
  devolvía 200 con el mismo contenido que `/placas-solares-murcia`, desperdiciando crawl budget pese
  al `<link rel="canonical">` de cada página). El dict `_REDIRECTS_HTML_LIMPIAS` es la lista blanca de
  slugs válidos — cualquier `.html` no listado da 404 en vez de caer al `mount`. Al añadir una página
  estática nueva, añadirla también a este dict.
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
- `google_reviews.py` — integración con Google Places API (New) para las reseñas reales de la
  empresa. `refrescar_resenas_cache()` llama a `_fetch_place_details()` para "es" y "en", guarda el
  resultado en un caché en memoria (`_cache`, persistido también en disco en
  `DATA_DIR/google_reviews_cache.json`) y, si el idioma "es" trae `rating`/`user_rating_count`,
  reescribe en caliente el nodo `"aggregateRating"` del JSON-LD de `static/index.html` y
  `static/en/index.html` (son estáticos sin templating server-side). Si el refresco de un idioma
  falla, se conserva el valor cacheado anterior de ese idioma en vez de vaciarlo. Se ejecuta
  automáticamente cada día a las 4:05 vía APScheduler (`api.py`, `_iniciar_scheduler_purga`) y puede
  forzarse manualmente desde el panel admin (`POST /api/admin/refrescar-resenas`). El frontend lee el
  caché ya calculado vía `GET /api/reviews?lang=es|en` (público, sin auth). Tests en
  `tests/test_google_reviews.py` (mockean `requests.get` y redirigen `CACHE_FILE`/
  `_AGGREGATE_RATING_FILES` a rutas temporales — nunca tocan los `static/*.html` reales).
- `guardrails.py` — `verificar_input`: firewall de entrada (bloquea off-topic/ataques, con reglas
  explícitas para no bloquear preguntas legítimas de negocio aunque suenen genéricas). `verificar_output`:
  revisa/corrige la respuesta antes de guardarla, con un fast-path regex (`_es_claramente_segura`) que
  evita la llamada al LLM para respuestas obviamente limpias.
- `database.py` — SQLite en modo WAL. Tabla `conversaciones` (estado, historial JSON, datos de
  contacto, coste acumulado, flag `gestionado`). Tabla `stats` con `coste_historico` (se alimenta del
  coste de conversaciones eliminadas, para no perder la cuenta al borrar leads desde el admin).
  `reset_conversacion()` limpia historial y datos de contacto pero **no** el coste acumulado ni
  `gestionado` — persisten a través de un reset.
- `admin_panel/admin.html` + `admin_panel/admin.js` — panel de administración (login propio + Basic
  Auth a nivel de servidor en `/admin`, doble capa). Viven fuera de `static/` a propósito: si
  estuvieran ahí, `StaticFiles` los serviría directamente sin pasar por `verificar_admin` (ya pasó,
  ver auditoría de seguridad). Se sirven vía `GET /admin` y `GET /admin.js`, ambas rutas protegidas
  por `Depends(verificar_admin)` en `api.py`. Tabla de leads con filtros por texto (insensible a
  tildes) y por estado, marcar gestionado, eliminar, coste total acumulado. La lógica vive en
  `admin.js` (externo) — antes estaba inline en `admin.html` (`<script>` + `onclick`/`onkeypress`/
  `oninput`) y la
  CSP (`script-src 'self'`, sin `unsafe-inline`) lo bloqueaba en silencio, dejando el botón "Entrar al
  Panel" sin hacer nada; no volver a poner JS ni handlers inline en esta página (ver CSP en "Detalles
  importantes"). El CSS también es propio y autocontenido — antes dependía del CDN de
  `cdn.tailwindcss.com`, que la misma CSP bloqueaba dejando `/admin` sin estilos.
- `static/script.js` — además de la UI (chat, formulario, contadores, reveals, tarjetas spotlight),
  `setupStory()` monta un canvas WebGL fijo a pantalla completa (`#sss-story`, detrás de todo el
  contenido) que dibuja un shader de 7 actos (`ACTO I` sol → `ACTO VII` amanecer) controlado por el
  progreso de scroll de **toda la página** (`scrollTop / (scrollHeight - clientHeight)`, suavizado con
  lerp). El "sol" que se ve en el hero no es un asset del hero — es este canvas de fondo asomando a
  través de los overlays semitransparentes de `#inicio` (ver gotcha en "Detalles importantes").
  También dispara eventos de negocio a GA4 vía `trackEvent()` (no-op si `gtag` no existe, i.e. el
  usuario rechazó cookies): `generate_lead` al enviar con éxito el formulario del hero, `chat_start` en
  el primer mensaje del chat, y `contact_click` (delegación global de clic sobre cualquier
  `tel:`/`wa.me`/`mailto:` de la página) para teléfono/WhatsApp/email.
- `documentos/solsureste_base_conocimiento.txt` — fuente de verdad del RAG. Tras editarlo, ejecutar
  `python cargar_pdfs.py` y **reiniciar el proceso del servidor** (ver gotcha de ChromaDB abajo).
- `test_conversacion.sh` — regresión end-to-end vía curl+jq contra un servidor ya corriendo.
- `static/faq.html` — página `/faq` con las 9 preguntas frecuentes reales (acordeón `<details>`),
  schema `FAQPage` + `BreadcrumbList`. Autocontenida (su propio `<style>`, sin depender de
  `styles.css`). Si se edita el contenido, mantener el texto sincronizado con la sección "FAQ" de
  `documentos/solsureste_base_conocimiento.txt`. El JSON-LD `FAQPage` vive únicamente aquí (no en
  `static/index.html` ni `static/en/index.html`, que solo enlazan a esta página vía una tarjeta
  teaser): duplicarlo ahí violaba las directrices de datos estructurados de Google, que exigen que el
  contenido marcado esté visible en la misma página (auditoría SEO).
- `static/aviso-legal.html`, `static/privacidad.html`, `static/cookies.html` — páginas legales
  (rutas `/aviso-legal`, `/privacidad`, `/cookies`), mismo patrón autocontenido que `faq.html`. El
  contenido de `privacidad.html` describe los tratamientos reales (RAG en `agencia.db`, Google
  Calendar, CRM, email de alerta, GA4) — si se añade una integración nueva que trate datos
  personales, actualizar esta página también.
- `static/consent.js` — banner de consentimiento de cookies; solo carga `gtag.js` (GA4, ID
  `G-X15TLEX3MB`) y el script de Microsoft Clarity (Project ID `xi6zd7zrwz`) tras aceptación explícita,
  guardada en `localStorage['sss_cookie_consent']`. Incluido en todas las páginas públicas
  (`index.html`, `faq.html`, y las 3 legales). Cualquier script de terceros nuevo que se añada aquí
  necesita también su dominio en la CSP de `api.py` (ver "Detalles importantes") o se bloquea en
  silencio igual que le pasó a Clarity la primera vez.
- `static/manifest.json` — manifest PWA mínimo (iconos `icon-192.png`/`icon-512.png` generados desde
  `static/images/logo.jpg`).
- `documentos/plantilla-pagina-seo.html` — plantilla comentada usada como base para las páginas de
  ciudad/provincia de abajo. Vive fuera de `static/` a propósito para que `StaticFiles` nunca la sirva
  por accidente. Sigue sirviendo de base para futuras páginas de servicio (residencial/industrial/
  huertos solares/mantenimiento), aún no implementadas. Trae su propio comentario-guía de 6 pasos y
  placeholders (`{{TITLE}}`, `{{DESCRIPTION}}`, `{{URL}}`, `{{JSON_LD}}`, `{{LABEL}}`, `{{H1}}`,
  `{{CONTENIDO_ESPECÍFICO_NO_DUPLICADO}}`) — al usarla para una página nueva, seguir el mismo patrón de
  registro que las páginas `placas-solares-*`: ruta nueva en `api.py` (`@app.get("/<slug>")` +
  `FileResponse`), añadir la URL a `static/sitemap.xml`, y enlazarla desde la página pilar/relacionada
  correspondiente vía `.cluster-links`.
- `static/sitemap.xml` — cada `<url>` lleva `loc`/`lastmod`/`changefreq`/`priority`. **Actualizar
  `lastmod` a mano** (formato `YYYY-MM-DD`) cada vez que se edite contenido visible de una página que
  ya esté en el sitemap — no hay ningún mecanismo automático que lo haga por ti.
- `static/placas-solares-{murcia,alicante}.html` — páginas **pilar** de SEO local (rutas
  `/placas-solares-murcia` y `/placas-solares-alicante`), cobertura a nivel provincia/región. Enlazan
  a sus páginas de ciudad correspondientes vía `.cluster-links`. Schema `Service` (no `LocalBusiness`
  duplicado) con `areaServed` de tipo `AdministrativeArea`.
- `static/placas-solares-{lorca,cartagena,molina-de-segura,orihuela,torrevieja,orihuela-costa,
  pilar-de-la-horadada}.html` — páginas **clúster** de ciudad/comarca (modelo pilar→clúster, ver
  "Detalles importantes"). Cada una enlaza de vuelta a su pilar vía breadcrumb + enlace inline.
  Lorca/Cartagena/Orihuela expanden los casos reales que también aparecen (de forma resumida, con
  teaser "Leer caso completo →") en la sección "Resultados reales" de `static/index.html`. Schema
  `Service` con `areaServed` de tipo `City`, con dos excepciones deliberadas: **Molina de Segura**
  (la sede real) tiene el `provider` enriquecido a `HomeAndConstructionBusiness` con `PostalAddress`
  y `geo` reales en vez del `Organization` genérico del resto; **Orihuela Costa** usa
  `areaServed: {"@type":"Place","containedInPlace":{"@type":"City","name":"Orihuela"}}` en vez de
  `City` directamente, porque no es un municipio independiente sino una franja costera dentro de
  Orihuela.
- `static/en/index.html` — traducción manual completa de la home al inglés, servida en la ruta
  `/en` (registrada explícitamente en `api.py`, fuera del patrón de las demás páginas). `hreflang`
  recíproco con `static/index.html` (`es`↔`en`, `x-default` apunta siempre a `/`). No usa el
  mecanismo `data-i18n`/`setLang()` de `script.js` (ese es solo un toggle de texto post-carga, no
  apto para contenido inicial indexable) — es un HTML separado y autónomo. **Coste de
  mantenimiento**: al editar texto visible en `static/index.html`, revisar si aplica el mismo
  cambio en `static/en/index.html` (estructura, clases e IDs deben mantenerse idénticos entre
  ambos; solo cambia el texto). El saludo inicial del chat (`greetingText()` en `script.js`) sí es
  compartido y ya es sensible al idioma vía `document.documentElement.lang` — no duplicar esa
  lógica al traducir. La sincronización estructural está cubierta por
  `tests/test_html_estructura_sincronizada.py`: compara el conjunto de `id="..."` de ambos ficheros y
  falla si uno tiene un `id` que el otro no tiene, así que un cambio de estructura sin traducir revienta
  en CI en vez de descubrirse manualmente.

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
- **La CSP de `api.py` (`_CSP`) es restrictiva por defecto y bloquea en silencio — ya ha mordido tres
  veces**: `script-src` solo permite `'self'` más los dominios explícitamente listados (hoy
  `googletagmanager.com` y `clarity.ms`); no hay `unsafe-inline` en `script-src` (sí en `style-src`, ver
  comentario en el propio archivo). Cualquier `<script>` inline, atributo `onclick`/`oninput`/etc., o
  script de un CDN/tercero nuevo que no esté en la lista **no lanza ningún error en el servidor** — el
  navegador simplemente lo descarta, y el síntoma es "el botón no hace nada" o "la página no tiene
  estilos", sin pista alguna en los logs de `agencia.log`. Ya pasó con el CDN de Tailwind en
  `admin.html`, con los handlers inline del login de `admin.html`, y con el script de Microsoft Clarity
  en `consent.js`. Regla: cualquier script/CDN de terceros nuevo necesita su dominio añadido a
  `script-src` (y a `connect-src` si además envía datos por fetch/beacon) antes de darlo por probado —
  comprobarlo en la consola del navegador (pestaña Network/Console), no basta con mirar que el deploy
  fue bien.
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
  en `api.py` con el mismo patrón `@app.get("/placas-solares-<slug>")` (y a `_REDIRECTS_HTML_LIMPIAS`,
  ver más arriba). Las páginas de ciudad geográficamente cercanas también se enlazan **entre sí**, no
  solo verticalmente con su pilar: Lorca↔Cartagena↔Molina de Segura (mismo pilar, Región de Murcia) y
  Torrevieja↔Orihuela Costa↔Pilar de la Horadada (mismo pilar, Alicante) — al añadir una ciudad nueva,
  enlazarla también con sus vecinas reales de comarca/costa, no solo con el pilar.
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
- **Contenido fiscal citado en `placas-solares-*`: verificar siempre la fuente primaria de la
  ordenanza/administración, nunca un blog SEO comercial**: varias páginas de ciudad citan ayudas y
  deducciones fiscales reales para diferenciarse de la plantilla compartida (deducción autonómica del
  IRPF en la Comunitat Valenciana y en la Región de Murcia, bonificaciones del IBI de los ayuntamientos
  de Orihuela y Torrevieja). Cada cifra se verificó contra la fuente oficial (sede.gva.es, Agencia
  Tributaria, BOP/ordenanza municipal en PDF), no contra agregadores comerciales tipo sotysolar.es o
  esirenovables.es — estos se contradicen entre sí con frecuencia (p. ej. daban 30% y 50% distintos
  para el mismo IBI de Torrevieja; el PDF oficial del BOP confirmó 50%). Ojo también con el **alcance
  exacto** de cada bonificación antes de citarla: la del ICIO del Ayuntamiento de Pilar de la Horadada
  existe (50%) pero su ordenanza la limita explícitamente a "aprovechamiento térmico" de energía
  solar — no cubre las instalaciones fotovoltaicas que vende la empresa, así que a propósito **no** se
  citó en esa página pese a existir. Al tocar estas páginas o añadir una ciudad nueva, no reutilizar
  una cifra fiscal de otro municipio/comunidad autónoma sin comprobar que aplica literalmente ahí.
