# Solsureste Solar

Sitio web público de Solsureste Solar — instalación de placas solares en Murcia y Alicante.

Static site, sin build step: HTML + CSS + JS puro.

## Estructura

- `index.html` — toda la maquetación de la página.
- `styles.css` — estilos base, keyframes de animación y estados hover/focus.
- `script.js` — comportamiento: fondo WebGL de scroll-story, partículas del hero,
  red eléctrica animada de la barra de stats, contadores, reveals al hacer scroll,
  tarjetas con efecto spotlight, chat de demo y formulario de contacto.

## Desarrollo local

No requiere build ni dependencias. Sirve la carpeta con cualquier servidor estático:

```bash
python3 -m http.server 8000
# abre http://localhost:8000
```

## Despliegue

Cada push a `main` publica el sitio en GitHub Pages automáticamente
(ver `.github/workflows/pages.yml`).

## Pendiente

- Sustituir los recuadros de imagen placeholder (hero + 3 casos de éxito) por fotos reales.
- El formulario del hero y el chat del hero son actualmente demos visuales
  (respuestas predefinidas, sin backend conectado).
