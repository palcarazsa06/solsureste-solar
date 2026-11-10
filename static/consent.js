(function () {
  var GA_ID = 'G-X15TLEX3MB';
  var CLARITY_ID = 'xi6zd7zrwz';
  var KEY = 'sss_cookie_consent';

  function loadGA() {
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { dataLayer.push(arguments); };
    gtag('js', new Date());
    gtag('config', GA_ID);
  }

  function loadClarity() {
    (function (c, l, a, r, i, t, y) {
      c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
      t = l.createElement(r); t.async = 1; t.src = 'https://www.clarity.ms/tag/' + i;
      y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
    })(window, document, 'clarity', 'script', CLARITY_ID);
  }

  function loadAnalytics() { loadGA(); loadClarity(); }

  function leer() {
    try { return localStorage.getItem(KEY); } catch (_) { return null; }
  }
  function guardar(valor) {
    try { localStorage.setItem(KEY, valor); } catch (_) { /* modo privado: no se recuerda */ }
  }

  // Al retirar el consentimiento hay que borrar también las cookies que ya dejaron GA y
  // Clarity (_ga, _ga_<id>, _clck, _clsk...). Se prueban el host actual y el dominio padre
  // porque GA las escribe en el dominio de nivel superior (.solsurestesolar.com).
  function borrarCookiesAnaliticas() {
    var host = location.hostname;
    var dominios = ['', host, '.' + host.replace(/^www\./, '')];
    document.cookie.split(';').forEach(function (c) {
      var nombre = c.split('=')[0].trim();
      if (!/^(_ga|_gid|_gat|_cl|CLID|MUID)/.test(nombre)) return;
      dominios.forEach(function (d) {
        document.cookie = nombre + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + (d ? '; domain=' + d : '');
      });
    });
  }

  var banner = null;

  function mostrarBanner() {
    if (banner) return;
    var estabaAceptado = leer() === 'accepted';
    banner = document.createElement('div');
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Preferencias de cookies');
    banner.className = 'sss-cookie-bar';
    banner.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#0e0e11;border-top:1px solid rgba(255,180,61,.25);padding:16px 20px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;font-family:"Space Grotesk",system-ui,sans-serif;color:#f4f3f0';
    banner.innerHTML = '<p style="margin:0;font-size:13.5px;max-width:640px;color:rgba(244,243,240,.8)">Usamos cookies analíticas (Google Analytics y Microsoft Clarity) para entender cómo se usa la web. Puedes aceptarlas o rechazarlas, y cambiar de opinión cuando quieras desde «Configurar cookies» al pie de cada página. Más info en <a href="/cookies" style="color:#FFB43D">Política de cookies</a>.</p><div style="display:flex;gap:10px;flex-shrink:0"><button id="sss-cookie-reject" class="sss-cookie-btn">Rechazar</button><button id="sss-cookie-accept" class="sss-cookie-btn">Aceptar</button></div>';
    document.body.appendChild(banner);
    document.getElementById('sss-cookie-accept').addEventListener('click', function () {
      guardar('accepted');
      if (!estabaAceptado) loadAnalytics();
      cerrar();
    });
    document.getElementById('sss-cookie-reject').addEventListener('click', function () {
      guardar('rejected');
      cerrar();
      if (estabaAceptado) {
        // Los scripts de GA/Clarity ya están en memoria: se borran sus cookies y se recarga
        // para que dejen de ejecutarse en esta misma visita.
        borrarCookiesAnaliticas();
        location.reload();
      }
    });
    var primero = document.getElementById('sss-cookie-reject');
    if (primero && document.activeElement && document.activeElement.hasAttribute &&
        document.activeElement.hasAttribute('data-cookie-settings')) {
      primero.focus();
    }
  }

  function cerrar() {
    if (banner) { banner.remove(); banner = null; }
  }

  // Cualquier enlace con data-cookie-settings reabre el banner. Es un <a href="/cookies">,
  // así que sin JavaScript sigue llevando a la política de cookies.
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-cookie-settings]') : null;
    if (!el) return;
    e.preventDefault();
    if (document.body) mostrarBanner();
  });

  var stored = leer();
  if (stored === 'accepted') { loadAnalytics(); return; }
  if (stored === 'rejected') { return; }

  if (document.body) {
    mostrarBanner();
  } else {
    document.addEventListener('DOMContentLoaded', mostrarBanner);
  }
})();
