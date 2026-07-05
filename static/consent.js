(function () {
  var GA_ID = 'G-X15TLEX3MB';
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

  var stored = localStorage.getItem(KEY);
  if (stored === 'accepted') { loadGA(); return; }
  if (stored === 'rejected') { return; }

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.createElement('div');
    bar.setAttribute('role', 'dialog');
    bar.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#0e0e11;border-top:1px solid rgba(255,180,61,.25);padding:16px 20px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;font-family:"Space Grotesk",system-ui,sans-serif;color:#f4f3f0';
    bar.innerHTML = '<p style="margin:0;font-size:13.5px;max-width:640px;color:rgba(244,243,240,.8)">Usamos cookies analíticas (Google Analytics) para entender cómo se usa la web. Puedes aceptarlas o rechazarlas. Más info en <a href="/cookies" style="color:#FFB43D">Política de cookies</a>.</p><div style="display:flex;gap:10px;flex-shrink:0"><button id="sss-cookie-reject" style="height:38px;padding:0 16px;border-radius:9px;border:1px solid rgba(255,255,255,.15);background:transparent;color:#f4f3f0;cursor:pointer">Rechazar</button><button id="sss-cookie-accept" style="height:38px;padding:0 18px;border-radius:9px;border:none;background:linear-gradient(135deg,#FFB43D,#F5921E);color:#1a1205;font-weight:600;cursor:pointer">Aceptar</button></div>';
    document.body.appendChild(bar);
    document.getElementById('sss-cookie-accept').addEventListener('click', function () {
      localStorage.setItem(KEY, 'accepted'); loadGA(); bar.remove();
    });
    document.getElementById('sss-cookie-reject').addEventListener('click', function () {
      localStorage.setItem(KEY, 'rejected'); bar.remove();
    });
  });
})();
