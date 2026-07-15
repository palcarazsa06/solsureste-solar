# Contexto SEO — solsurestesolar.com (para Claude Code)

> Este documento lo preparó otra sesión de Claude con acceso al conector de Google Search Console de este dominio. Contiene el diagnóstico actual y lo que se espera de ti en este proyecto. Léelo entero antes de tocar nada, audita el código con estos datos en mente, y devuelve un plan priorizado **antes** de hacer cambios.

Fecha del análisis: 14 julio 2026
Dominio: `solsurestesolar.com` (propiedad GSC: `sc-domain:solsurestesolar.com`)
Sector: instalación de placas solares / autoconsumo, zona Región de Murcia y Costa Blanca (Cartagena, Murcia, Lorca, Molina de Segura, Alicante, Torrevieja, Orihuela, Pilar de la Horadada)
Stack: HTML/CSS estático (sin framework)

## 1. Situación general

Sitio muy nuevo en Search Console: no hay datos antes del 24 de junio de 2026. En estos ~19 días:

- 10 clics, 244 impresiones totales, CTR ~4%
- Posición media desktop: 38 — posición media móvil: 9.8 (diferencia grande, hay que averiguar por qué)
- La posición media **está empeorando semana a semana**: a finales de junio rondaba 4-8, entre el 6 y el 12 de julio cayó a 28-60
- Es muy probable que ese puñado de clics/impresiones sea tráfico de pruebas propias, no usuarios reales todavía

## 2. Lo que NO es el problema (ya verificado en GSC)

- Home y páginas de servicio inspeccionadas (`/`, `/placas-solares-cartagena`) están **indexadas correctamente**, `robots.txt` permite el rastreo, no hay bloqueos de indexación
- Se detectaron rich results (review snippets en home, breadcrumbs en páginas de servicio)
- El sitemap (`https://solsurestesolar.com/sitemap.xml`, 15 URLs) se descarga sin errores ni warnings

Conclusión: no hay un problema técnico bloqueante de indexación. El problema es de **autoridad y calidad/diferenciación de contenido**, típico de un sitio nuevo sin backlinks compitiendo por keywords locales.

## 3. Páginas de servicio y su posición actual (28 días)

| Página | Impresiones | Clics | Posición media |
|---|---|---|---|
| `/` (home) | 62 | 7 | 4.9 |
| `/placas-solares-cartagena` | 26 | 0 | 69.2 |
| `/placas-solares-alicante` | 23 | 0 | 72.8 |
| `/placas-solares-murcia` | 11 | 0 | 44.2 |
| `/placas-solares-lorca` | 7 | 0 | 55.9 |
| `/placas-solares-molina-de-segura` | 7 | 0 | 31.1 |
| `/placas-solares-torrevieja` | 5 | 0 | 77.8 |
| `/placas-solares-orihuela` | 4 | 0 | 48.8 |
| `/placas-solares-pilar-de-la-horadada` | 1 | 0 | 7.0 |
| `/faq` | 4 | 0 | 8.3 |
| `/en` | 11 | 0 | 37.6 |

Todas las páginas de ciudad (salvo la home) están fuera de las primeras 3-4 páginas de resultados: cero clics.

## 4. Keywords donde el sitio ya tiene impresiones (todas en posiciones muy bajas)

`instalación placas solares cartagena` (pos. 84), `placas solares en murcia` (pos. 101), `placas solares casa campo alicante` (pos. 64), `placas solares industriales murcia` (pos. 85), `instalar placas solares naves refrigeración` (pos. 83), `placas solares en torrevieja` (pos. 80), `placas solares costa blanca` (pos. 79), `placas solares lorca` (pos. 46.5), `instalacion placas solares molina de segura` (pos. 27-29)

Son exactamente las keywords que se esperaría que este negocio gane — el interés de búsqueda existe, pero el sitio no está lo bastante fuerte todavía para competir por ellas.

## 5. Lo que YO (el dueño del negocio) voy a gestionar fuera del código

No lo toques ni lo repliques en el repo, pero ten el contexto:

- Campaña de Google Ads de prueba (200-250€), acotada a 1-2 ciudades prioritarias
- Google Business Profile por zona de servicio + gestión de reseñas
- Backlinks externos: directorios locales, gremios/asociaciones de energía solar, prensa local, colaboraciones con proveedores
- Publicación y promoción del blog una vez tengamos los artículos

## 6. Lo que necesito que TÚ (Claude Code) hagas en este repo

Empieza por auditar, no por cambiar código. Devuélveme un resumen priorizado y espera mi confirmación antes de tocar producción. En concreto quiero que revises:

1. **Contenido duplicado entre páginas de ciudad.** Sospecho que las páginas `/placas-solares-*` son una plantilla con el nombre de la ciudad cambiado y poco más. Confírmalo y, si es así, propón cómo diferenciar cada una de verdad (datos locales, casos, zonas concretas, ayudas/subvenciones de esa ciudad, testimonios locales) — no solo cambiar el topónimo.
2. **Title tags, meta descriptions y H1** de cada página de servicio: revisa si son únicos, si incluyen la keyword local de forma natural, y si el meta description invita al clic (nuestro CTR es del 4%, muy bajo).
3. **Datos estructurados (schema.org):** confirma si hay `LocalBusiness`/`Service`/`FAQPage` y si están bien implementados por página, no solo en la home.
4. **Enlazado interno:** cómo están enlazadas entre sí las páginas de ciudad y si hay una estructura clara hub → páginas de servicio.
5. **Diferencia de rendimiento desktop vs móvil.** Nuestra posición media en desktop (38) es mucho peor que en móvil (9.8), lo cual es inusual. Revisa si hay algo en el CSS/HTML que cargue distinto o peor en desktop, y pasa Lighthouse si puedes para comparar Core Web Vitals.
6. **`sitemap.xml` y `robots.txt` locales del repo:** confirma que coinciden con lo que ve GSC y que no falta ninguna URL importante.
7. **Borradores de contenido de blog** (una vez termines la auditoría, si te lo pido): 2-3 artículos long-tail tipo "cuánto cuesta una instalación de placas solares en Murcia", "ayudas y subvenciones autoconsumo Región de Murcia 2026", "placas solares para nave industrial: qué necesitas saber". Van orientados a keywords donde ya tenemos alguna impresión pero cero contenido dedicado.

## 7. Reglas

- No despliegues ni hagas commit de cambios sin que yo los revise primero.
- Si encuentras contenido duplicado o thin content, dímelo explícitamente con ejemplos, no lo arregles en silencio.
- Prioriza: primero lo que puede mover la aguja rápido (title/meta/H1, diferenciación de las páginas de ciudad con más impresiones: Cartagena, Alicante, Murcia), después lo estructural (schema, performance).
