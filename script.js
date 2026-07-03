// Solsureste Solar — behavior, ported 1:1 from the Claude Design prototype
// (project/Solsureste Solar.dc.html componentDidMount + methods).
// The prototype's dead code (old irradiation-map / house sections the user
// deleted mid-design, and the mid-page black-hole/sun band later replaced by
// the story canvas) targeted DOM nodes that no longer exist and is dropped
// here rather than ported.
(function () {
  'use strict';

  const S = {
    reduce: false,

    init() {
      const root = document.getElementById('sss-root');
      if (!root) return;
      this.reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.buildTechCards();
      this.buildWhyCards();
      this.buildSteps();
      requestAnimationFrame(() => {
        root.classList.add('js-ready');
        this.setupReveals();
        this.setupCounters();
      });
      this.setupParticles();
      this.setupGlow();
      this.setupParallax();
      this.setupScroll();
      this.setupMagnetic();
      this.setupSpotlight();
      this.setupStory();
      this.setupGrid();
      this.setupStepLine();
      this.setupFinance();
      this.initChat();
      this.setupBindings();
    },

    setupBindings() {
      const es = document.getElementById('sss-lang-es');
      const en = document.getElementById('sss-lang-en');
      if (es) es.addEventListener('click', () => this.setLang('es'));
      if (en) en.addEventListener('click', () => this.setLang('en'));
      const heroForm = document.getElementById('sss-hero-form');
      if (heroForm) heroForm.addEventListener('submit', (e) => this.handleHeroSubmit(e));
      const chatForm = document.getElementById('sss-chat-form');
      if (chatForm) chatForm.addEventListener('submit', (e) => this.handleChatSubmit(e));
      const chatReset = document.getElementById('sss-chat-reset');
      if (chatReset) chatReset.addEventListener('click', () => this.resetChat());
    },

    // ---------- dynamic card builders ----------
    icon(p) { return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>'; },

    buildTechCards() {
      const grid = document.querySelector('.sss-techgrid');
      if (!grid) return;
      const cards = [
        ['<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>', 'Análisis de consumo real', 'Estudiamos tus facturas de los últimos 12 meses para dimensionar exactamente el sistema que necesitas, sin sobredimensionar ni quedarte corto.'],
        ['<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>', 'Modelado 3D de tu cubierta', 'Diseño de la distribución óptima de paneles con simulación de sombras en tiempo real, orientación e inclinación específica de tu tejado.'],
        ['<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>', 'Previsión de generación mes a mes', 'Estimación de producción con datos de irradiación específicos de tu municipio y calibrados con nuestras instalaciones reales en la zona.'],
        ['<path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>', 'ROI, amortización y VAN', 'Cuánto ahorras, cuándo recuperas la inversión y qué rentabilidad anual obtienes durante toda la vida útil de la instalación.'],
        ['<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>', 'Tramitación incluida', 'Nos ocupamos de toda la burocracia: licencias municipales, legalización ante la distribuidora y acceso a bonificaciones autonómicas.'],
        ['<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>', 'Garantía de 25 años', 'Garantía de mano de obra y rendimiento mínimo garantizado en módulos. Si no produce lo que prometemos, lo resolvemos nosotros.'],
      ];
      grid.innerHTML = cards.map(c =>
        '<div data-reveal data-spotlight style="border-radius:20px;border:1px solid rgba(255,255,255,.07);background:#141417;padding:26px;transition:transform .4s,border-color .4s,box-shadow .4s">'
        + '<span style="display:flex;height:46px;width:46px;align-items:center;justify-content:center;border-radius:13px;background:rgba(255,180,61,.14);color:#FFB43D">' + this.icon(c[0]) + '</span>'
        + '<h3 style="margin:18px 0 0;font-size:17px;font-weight:600">' + c[1] + '</h3>'
        + '<p style="margin:12px 0 0;font-size:15px;line-height:1.6;color:rgba(244,243,240,.64)">' + c[2] + '</p></div>'
      ).join('');
    },

    buildWhyCards() {
      const grid = document.querySelector('.sss-whygrid');
      if (!grid) return;
      const cards = [
        ['<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>', 'Instalador de referencia en el sureste', 'Más de 25 años en el sector diseñando, instalando y manteniendo instalaciones solares en Murcia y Alicante.'],
        ['<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>', 'Sin intermediarios ni comerciales', 'Nuestros ingenieros personalizan tu oferta sin intermediarios que encarezcan la instalación.'],
        ['<path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12V6h16v6"/><path d="m4 12 4 2h8l4-2"/><path d="M2 19h20"/>', 'Equipo y maquinaria propios', 'No subcontratamos nada. Eso nos da control total sobre los plazos, la calidad de ejecución y el coste final.'],
        ['<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>', 'Tramitación burocrática incluida', 'Tramitamos la licencia de obra y el registro en la Dirección General de Industria de tu Comunidad.'],
        ['<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.1-3.1c.3-.3.9-.2 1 .2a6 6 0 0 1-8.3 7.1l-7.9 7.9a1 1 0 0 1-3-3l7.9-7.9a6 6 0 0 1 7.1-8.3c.4.1.5.7.2 1z"/>', 'Soporte post venta real', 'Control de la monitorización, revisiones periódicas según normativa, reparaciones, limpieza...'],
      ];
      grid.innerHTML = cards.map(c =>
        '<div data-reveal data-spotlight style="display:flex;align-items:flex-start;gap:15px;border-radius:20px;border:1px solid rgba(255,255,255,.07);background:#141417;padding:26px;transition:transform .4s,border-color .4s,box-shadow .4s">'
        + '<span style="flex-shrink:0;display:flex;height:46px;width:46px;align-items:center;justify-content:center;border-radius:13px;background:rgba(255,180,61,.14);color:#FFB43D">' + this.icon(c[0]) + '</span>'
        + '<div><h3 style="margin:0;font-size:16px;font-weight:600">' + c[1] + '</h3>'
        + '<p style="margin:8px 0 0;font-size:15px;line-height:1.55;color:rgba(244,243,240,.64)">' + c[2] + '</p></div></div>'
      ).join('');
    },

    buildSteps() {
      const wrap = document.querySelector('.sss-steps');
      if (!wrap) return;
      const steps = [
        'Agenda una visita con nuestro asistente o rellena nuestro formulario y contactamos contigo.',
        'Hacemos una visita a tu domicilio para determinar las particularidades de tu instalación y ver la idoneidad de tus cubiertas.',
        'En base a tus consumos de energía y a las características de tu vivienda, elaboramos una propuesta específica personalizada.',
        'Te presentamos la oferta y te ofrecemos nuestras formas de pago flexibles.',
        'Si te parece aceptable nuestra propuesta, <strong style="color:#f4f3f0">en dos semanas podrías tener tu instalación.</strong>',
      ];
      wrap.style.position = 'relative';
      const line = '<div style="position:absolute;left:23px;top:26px;bottom:26px;width:2px;background:rgba(255,180,61,.14);border-radius:2px;z-index:0"></div>'
        + '<div id="sss-stepfill" style="position:absolute;left:23px;top:26px;width:2px;height:0;background:linear-gradient(180deg,#FFD89A,#F5921E);border-radius:2px;z-index:0;box-shadow:0 0 14px rgba(255,180,61,.75)"></div>';
      wrap.innerHTML = line + steps.map((s, i) =>
        '<div data-reveal style="position:relative;z-index:1;display:flex;align-items:flex-start;gap:18px">'
        + '<div data-stepcircle style="flex-shrink:0;display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:50%;background:linear-gradient(135deg,rgba(255,180,61,.26),rgba(224,122,12,.2));color:#FFD89A;font-weight:700;font-size:18px;border:1px solid rgba(255,180,61,.3);transition:background .4s,box-shadow .4s,color .4s,border-color .4s">' + (i + 1) + '</div>'
        + '<p style="margin:0;padding-top:11px;font-size:16.5px;line-height:1.55;color:rgba(244,243,240,.82)">' + s + '</p></div>'
      ).join('');
    },

    setupStepLine() {
      const wrap = document.querySelector('.sss-steps');
      const fill = document.getElementById('sss-stepfill');
      if (!wrap || !fill) return;
      const circles = Array.from(wrap.querySelectorAll('[data-stepcircle]'));
      const lit = (c) => { c.style.background = 'linear-gradient(135deg,#FFE0A0,#F5921E)'; c.style.color = '#1a1205'; c.style.borderColor = 'transparent'; c.style.boxShadow = '0 6px 22px rgba(255,180,61,.55),0 0 0 4px rgba(255,180,61,.14)'; };
      const dim = (c) => { c.style.background = 'linear-gradient(135deg,rgba(255,180,61,.26),rgba(224,122,12,.2))'; c.style.color = '#FFD89A'; c.style.borderColor = 'rgba(255,180,61,.3)'; c.style.boxShadow = 'none'; };
      if (this.reduce) { fill.style.height = (wrap.offsetHeight - 52) + 'px'; circles.forEach(lit); return; }
      const update = () => {
        const r = wrap.getBoundingClientRect();
        const vh = window.innerHeight;
        const p = Math.max(0, Math.min(1, (vh * 0.72 - r.top) / (r.height * 0.82)));
        const trackH = r.height - 52;
        fill.style.height = (p * trackH) + 'px';
        const fillBottom = r.top + 26 + p * trackH;
        circles.forEach(c => {
          const cr = c.getBoundingClientRect();
          if (cr.top + cr.height / 2 <= fillBottom + 5) lit(c); else dim(c);
        });
      };
      update();
      window.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', update);
    },

    // ---------- flujo €→sol (financiacion) ----------
    setupFinance() {
      const sec = document.getElementById('financiacion');
      const cv = document.getElementById('sss-fin-fx');
      if (!sec || !cv) return;
      const ctx = cv.getContext('2d');
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      let W = 0, H = 0;
      const resize = () => { W = sec.clientWidth; H = sec.offsetHeight; cv.width = Math.max(1, W * dpr); cv.height = Math.max(1, H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
      resize(); window.addEventListener('resize', resize);
      if (window.ResizeObserver) { try { new ResizeObserver(resize).observe(sec); } catch (_) {} }
      const spawn = (init) => ({ x: Math.random() * W, y: init ? Math.random() * H : H + 24, sp: 0.35 + Math.random() * 0.85, sz: 11 + Math.random() * 10, sw: Math.random() * 6.28, drift: (Math.random() - 0.5) * 0.5 });
      const N = this.reduce ? 0 : 26;
      const P = []; for (let i = 0; i < N; i++) P.push(spawn(true));
      const draw = () => {
        ctx.clearRect(0, 0, W, H);
        const sx = W * 0.5, sy = -30;
        const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, W * 0.42);
        g.addColorStop(0, 'rgba(255,185,70,.20)'); g.addColorStop(0.4, 'rgba(255,150,50,.05)'); g.addColorStop(1, 'rgba(255,150,50,0)');
        ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
        ctx.globalCompositeOperation = 'lighter';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        for (const p of P) {
          const dx = sx - p.x, dy = sy - p.y, d = Math.hypot(dx, dy) || 1;
          p.x += (dx / d) * p.sp * 0.45 + p.drift;
          p.y -= p.sp + (dy / d) * p.sp * 0.18;
          p.sw += 0.04;
          const prog = 1 - (p.y / H);
          const a = Math.max(0, Math.min(1, prog * 1.5)) * 0.85;
          const near = Math.max(0, 1 - d / (H * 0.55));
          ctx.font = '600 ' + p.sz.toFixed(0) + 'px "Space Grotesk",sans-serif';
          ctx.fillStyle = 'rgba(255,' + (188 + (near * 60 | 0)) + ',' + (90 + (near * 130 | 0)) + ',' + a.toFixed(2) + ')';
          ctx.fillText('€', p.x + Math.sin(p.sw) * 4, p.y);
          if (p.y < -34 || d < 26) Object.assign(p, spawn(false));
        }
        ctx.globalCompositeOperation = 'source-over';
        if (!this.reduce) this._finRaf = requestAnimationFrame(draw);
      };
      draw();
    },

    // ---------- motion ----------
    setupReveals() {
      const els = document.querySelectorAll('[data-reveal]');
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            const sibs = Array.from(e.target.parentElement ? e.target.parentElement.querySelectorAll(':scope > [data-reveal]') : []);
            const idx = sibs.indexOf(e.target);
            const delay = idx > 0 ? Math.min(idx, 6) * 80 : 0;
            setTimeout(() => e.target.classList.add('in'), delay);
            obs.unobserve(e.target);
          }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
      els.forEach(el => obs.observe(el));
    },

    setupCounters() {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(e => {
          if (!e.isIntersecting) return;
          const el = e.target;
          const target = +el.dataset.target;
          const prefix = el.dataset.prefix || '';
          const suffix = el.dataset.suffix || '';
          if (this.reduce) { el.textContent = prefix + target + suffix; obs.unobserve(el); return; }
          const dur = 1700, t0 = performance.now();
          const tick = (now) => {
            const p = Math.min((now - t0) / dur, 1);
            const ease = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
            el.textContent = prefix + Math.floor(ease * target) + suffix;
            if (p < 1) requestAnimationFrame(tick); else el.textContent = prefix + target + suffix;
          };
          requestAnimationFrame(tick);
          obs.unobserve(el);
        });
      }, { threshold: 0.6 });
      document.querySelectorAll('[data-counter]').forEach(el => obs.observe(el));
    },

    setupParticles() {
      const cv = document.getElementById('sss-hero-fx');
      const sec = document.getElementById('inicio');
      if (!cv || !sec) return;
      const ctx = cv.getContext('2d');
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      let W = 0, H = 0;
      const resize = () => {
        W = sec.clientWidth; H = sec.offsetHeight;
        cv.width = Math.max(1, W * dpr); cv.height = Math.max(1, H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      };
      resize();
      window.addEventListener('resize', resize);
      if (window.ResizeObserver) { try { new ResizeObserver(resize).observe(sec); } catch (_) {} }

      const mouse = { x: -9999, y: -9999, active: false };
      sec.addEventListener('mousemove', (e) => { const r = sec.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; mouse.active = true; }, { passive: true });
      sec.addEventListener('mouseleave', () => { mouse.active = false; mouse.x = -9999; mouse.y = -9999; });

      const spawn = (init) => {
        const x = Math.random() * W, y = init ? Math.random() * H : H + 14;
        return {
          x, y, px: x, py: y,
          vx: (Math.random() - 0.5) * 0.3,
          vy: -(0.35 + Math.random() * 1.05),
          r: 0.7 + Math.random() * 2.8,
          a: 0.32 + Math.random() * 0.6,
          tw: Math.random() * 6.283,
          tws: 0.012 + Math.random() * 0.032,
          hot: Math.random() < 0.3
        };
      };
      const N = this.reduce ? 30 : 140;
      const P = [];
      for (let i = 0; i < N; i++) P.push(spawn(true));

      const draw = (p) => {
        const fl = 0.55 + 0.45 * Math.sin(p.tw);
        const alpha = p.a * fl;
        const tg = ctx.createLinearGradient(p.px, p.py, p.x, p.y);
        tg.addColorStop(0, 'rgba(255,150,45,0)');
        tg.addColorStop(1, (p.hot ? 'rgba(255,210,130,' : 'rgba(255,165,60,') + (alpha * 0.5) + ')');
        ctx.strokeStyle = tg; ctx.lineWidth = Math.max(0.6, p.r * 0.9); ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(p.px, p.py); ctx.lineTo(p.x, p.y); ctx.stroke();
        const rad = p.r * 3.0;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, rad);
        if (p.hot) { g.addColorStop(0, 'rgba(255,246,224,' + alpha + ')'); g.addColorStop(0.4, 'rgba(255,200,104,' + (alpha * 0.6) + ')'); }
        else { g.addColorStop(0, 'rgba(255,198,90,' + alpha + ')'); g.addColorStop(0.4, 'rgba(255,148,48,' + (alpha * 0.5) + ')'); }
        g.addColorStop(1, 'rgba(255,140,40,0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(p.x, p.y, rad, 0, 6.2832); ctx.fill();
      };

      if (this.reduce) {
        ctx.clearRect(0, 0, W, H);
        ctx.globalCompositeOperation = 'lighter';
        for (const p of P) draw(p);
        ctx.globalCompositeOperation = 'source-over';
        return;
      }

      const step = () => {
        ctx.clearRect(0, 0, W, H);
        ctx.globalCompositeOperation = 'lighter';
        for (const p of P) {
          if (mouse.active) {
            const dx = p.x - mouse.x, dy = p.y - mouse.y;
            const d2 = dx * dx + dy * dy, R = 150;
            if (d2 < R * R) {
              const d = Math.sqrt(d2) || 1, f = (1 - d / R);
              p.vx += (dx / d) * f * 0.55 - (dy / d) * f * 0.45;
              p.vy += (dy / d) * f * 0.55 + (dx / d) * f * 0.45;
            }
          }
          p.px = p.x; p.py = p.y;
          p.x += p.vx; p.y += p.vy;
          p.vx *= 0.975;
          p.vy = p.vy * 0.985 - 0.004;
          if (p.vy > -0.2) p.vy -= 0.014;
          p.tw += p.tws;
          if (p.y < -16 || p.x < -26 || p.x > W + 26) { Object.assign(p, spawn(false)); continue; }
          draw(p);
        }
        ctx.globalCompositeOperation = 'source-over';
        this._heroRaf = requestAnimationFrame(step);
      };
      step();
    },

    setupGlow() {
      const glow = document.getElementById('sss-hero-glow');
      const sec = document.getElementById('inicio');
      if (!glow || !sec || this.reduce) return;
      sec.addEventListener('mousemove', (e) => {
        const r = sec.getBoundingClientRect();
        glow.style.left = (e.clientX - r.left) + 'px';
        glow.style.top = (e.clientY - r.top) + 'px';
        glow.style.opacity = '1';
      }, { passive: true });
      sec.addEventListener('mouseleave', () => { glow.style.opacity = '0'; });
    },

    setupParallax() {
      const media = document.getElementById('sss-hero-parallax');
      const sec = document.getElementById('inicio');
      if (!media || !sec || this.reduce) return;
      window.addEventListener('scroll', () => {
        const s = window.scrollY, h = sec.offsetHeight;
        if (s < h) media.style.transform = 'translateY(' + (s * 0.18) + 'px) scale(' + (1 + s / h * 0.08) + ')';
      }, { passive: true });
    },

    setupScroll() {
      const bar = document.getElementById('sss-progress');
      const header = document.getElementById('sss-header');
      const onScroll = () => {
        const d = document.documentElement;
        const max = d.scrollHeight - d.clientHeight;
        if (bar) bar.style.width = max > 0 ? (d.scrollTop / max * 100) + '%' : '0%';
        if (header) {
          if (window.scrollY > 8) { header.style.background = 'rgba(10,10,12,.9)'; header.style.boxShadow = '0 4px 30px rgba(0,0,0,.4)'; }
          else { header.style.background = 'rgba(10,10,12,.62)'; header.style.boxShadow = 'none'; }
        }
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    },

    setupMagnetic() {
      if (this.reduce) return;
      document.querySelectorAll('[data-magnetic]').forEach(btn => {
        btn.addEventListener('mousemove', (e) => {
          const r = btn.getBoundingClientRect();
          const x = e.clientX - r.left - r.width / 2;
          const y = e.clientY - r.top - r.height / 2;
          btn.style.transform = 'translate(' + (x * 0.25) + 'px,' + (y * 0.35) + 'px)';
        });
        btn.addEventListener('mouseleave', () => { btn.style.transform = 'translate(0,0)'; });
      });
    },

    setupSpotlight() {
      if (this.reduce) return;
      const apply = () => document.querySelectorAll('[data-spotlight]').forEach(card => {
        if (card.dataset.sp) return;
        card.dataset.sp = '1';
        card.addEventListener('mousemove', (e) => {
          const r = card.getBoundingClientRect();
          const px = (e.clientX - r.left) / r.width;
          const py = (e.clientY - r.top) / r.height;
          const rx = (py - 0.5) * -9;
          const ry = (px - 0.5) * 9;
          card.style.transition = 'transform .12s ease-out, border-color .4s, box-shadow .4s, background .4s';
          card.style.transform = 'perspective(920px) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg) translateY(-6px) scale(1.018)';
          card.style.borderColor = 'rgba(255,180,61,.38)';
          card.style.boxShadow = '0 26px 64px rgba(0,0,0,.55), inset 0 0 60px rgba(255,180,61,.05)';
          card.style.background = 'radial-gradient(360px circle at ' + (e.clientX - r.left) + 'px ' + (e.clientY - r.top) + 'px, rgba(255,180,61,.12), #141417 42%)';
        });
        card.addEventListener('mouseleave', () => {
          card.style.transition = 'transform .5s cubic-bezier(.16,1,.3,1), border-color .4s, box-shadow .4s, background .4s';
          card.style.transform = 'perspective(920px) rotateX(0deg) rotateY(0deg) translateY(0) scale(1)';
          card.style.borderColor = 'rgba(255,255,255,.07)';
          card.style.boxShadow = 'none';
          card.style.background = '#141417';
        });
      });
      apply();
      setTimeout(apply, 300);
    },

    // ---------- STORY: capa de fondo WebGL · 7 actos guiados por scroll ----------
    setupStory() {
      const cv = document.getElementById('sss-story');
      if (!cv) return;
      let gl;
      const opts = { antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' };
      try { gl = cv.getContext('webgl', opts) || cv.getContext('experimental-webgl', opts); } catch (e) {}
      if (!gl) { cv.style.background = 'radial-gradient(120% 80% at 50% 12%, rgba(255,150,40,.22), #06060c 55%)'; return; }
      const vsSrc = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}';
      const fsSrc = `precision highp float;
uniform vec2 uRes; uniform float uTime; uniform float uProg; uniform float uReduce;
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
float fbm(vec2 p){float v=0.0,a=0.5;for(int i=0;i<6;i++){v+=a*noise(p);p=p*2.02;a*=0.5;}return v;}

// ---- SOL (contenido idéntico al original) ----
vec3 sunColor(vec2 uv, float R, float spin, float t){
  vec3 col=vec3(0.0);
  float r=length(uv);
  float ang=atan(uv.y,uv.x);
  float rays=0.7+0.55*fbm(vec2(ang*7.0+spin*1.2, r*3.0-t*1.1));
  float aura=pow(R/max(r,0.0015),1.5)*rays;
  vec3 auraCol=mix(vec3(1.0,0.6,0.2),vec3(1.0,0.26,0.05),smoothstep(R,0.95,r));
  col+=auraCol*aura*0.32;
  col+=vec3(1.0,0.6,0.24)*exp(-r*2.1)*0.45;
  if(r>R && r<R+0.34){
    float fn=fbm(vec2(ang*5.0+spin, r*6.0-t*1.6));
    float fn2=fbm(vec2(ang*11.0-spin*0.7, r*12.0+t*1.2));
    float tongue=pow(max(fn*fn2*1.7,0.0),1.1);
    float fall=smoothstep(R+0.34,R,r);
    float flare=smoothstep(0.22,0.82,tongue*fall*fall);
    vec3 flcol=mix(vec3(1.0,0.95,0.62),vec3(1.0,0.20,0.04),smoothstep(R,R+0.34,r));
    flcol=mix(flcol,vec3(1.0,0.42,0.5),smoothstep(0.3,0.9,fn2)*0.35);
    col+=flcol*flare*1.7;
  }
  if(r<R){
    float zc=sqrt(max(R*R-r*r,0.0));
    vec3 s=vec3(uv.x,uv.y,zc)/R;
    float ca=cos(spin),sa=sin(spin);
    vec3 rp=vec3(s.x*ca+s.z*sa,s.y,-s.x*sa+s.z*ca);
    float gran=0.55*fbm(rp.xy*3.6+vec2(0.0,t))+0.45*fbm(rp.xy*8.5+rp.z*2.0-t*1.2);
    float veins=fbm(rp.xy*1.8+vec2(spin,0.0));
    vec3 c1=vec3(1.0,0.28,0.05),c2=vec3(1.0,0.6,0.12),c3=vec3(1.0,0.9,0.42),c4=vec3(1.0,1.0,0.95);
    vec3 base=mix(c1,c2,smoothstep(0.18,0.45,gran));
    base=mix(base,c3,smoothstep(0.45,0.68,gran));
    base=mix(base,c4,smoothstep(0.68,0.95,gran));
    float spot=smoothstep(0.70,0.76,fbm(rp.xy*1.4+vec2(spin*0.5,0.0)));
    base=mix(base,vec3(0.70,0.22,0.04),spot*0.45);
    base+=vec3(1.0,0.5,0.15)*pow(veins,2.0)*0.22;
    base*=0.68+0.4*s.z;
    base+=vec3(1.0,0.96,0.85)*pow(s.z,2.4)*0.4;
    col=base*1.55;
  }
  col+=vec3(1.0,0.7,0.34)*smoothstep(0.02,0.0,abs(r-R))*0.45;
  return col;
}

// luz vertical (rayo de energía)
float beam(vec2 uv, float cx, float w, float seed, float t){
  float d=abs(uv.x-cx);
  float core=smoothstep(w,0.0,d);
  float flick=0.6+0.4*fbm(vec2(uv.y*2.2+t*0.8+seed, seed*3.1));
  return core*flick;
}

void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  float t=uTime;
  float P=clamp(uProg,0.0,1.0);
  float vy=gl_FragCoord.y/uRes.y;          // 0 abajo .. 1 arriba
  vec3 col=vec3(0.0);

  // --- base espacial teñida por acto ---
  vec3 deep=vec3(0.018,0.020,0.045);
  vec3 warm=vec3(0.060,0.034,0.020);
  vec3 cool=vec3(0.016,0.034,0.060);
  vec3 dawn=vec3(0.075,0.052,0.030);
  float aWarm=smoothstep(0.20,0.0,P);
  float aCool=smoothstep(0.26,0.46,P)*smoothstep(0.74,0.52,P);
  float aDawn=smoothstep(0.82,1.0,P);
  vec3 baseC=mix(deep,warm,aWarm);
  baseC=mix(baseC,cool,aCool);
  baseC=mix(baseC,dawn,aDawn);
  col+=baseC*(0.55+0.55*vy);

  // --- nebulosa de energía a la deriva (siempre presente, mantiene vivo el fondo) ---
  {
    float neb=fbm(uv*1.5+vec2(t*0.04,-P*2.4+t*0.025));
    float neb2=fbm(uv*3.2-vec2(t*0.03,P*1.5));
    float n=pow(neb*0.7+neb2*0.3,2.1);
    vec3 nebCol=mix(vec3(1.0,0.5,0.18),vec3(0.18,0.6,1.0),aCool);
    nebCol=mix(nebCol,vec3(1.0,0.62,0.3),aDawn);
    col+=nebCol*n*0.22;
  }

  // --- starfield viajando hacia abajo ---
  {
    float travel=P*5.5;
    vec2 gv=vec2(uv.x,uv.y-travel)*16.0;
    vec2 cell=floor(gv); vec2 f=fract(gv)-0.5;
    float s=hash(cell);
    float on=step(0.92,s);
    vec2 off=(vec2(hash(cell+5.1),hash(cell+9.7))-0.5)*0.7;
    float d=length(f-off);
    float tw=0.55+0.45*sin(t*3.0+s*60.0);
    float core=smoothstep(0.04,0.0,d);
    float halo=smoothstep(0.15,0.0,d)*0.28;
    col+=vec3(0.78,0.84,1.0)*on*tw*(core+halo)*0.55*(0.9-0.5*aDawn);
  }

  // --- brasas de energía viajando (atraviesan el contenido, sensación de avance) ---
  {
    float spd=P*3.2+t*0.05;
    vec2 gv=vec2(uv.x*1.25,uv.y+spd)*6.5;
    vec2 cell=floor(gv); vec2 f=fract(gv)-0.5;
    float s=hash(cell+11.0);
    float on=step(0.80,s);
    vec2 off=(vec2(hash(cell+2.1),hash(cell+7.7))-0.5)*0.7;
    float d=length(f-off);
    float pulse=0.45+0.55*sin(t*2.4+s*40.0);
    float core=smoothstep(0.05,0.0,d);
    float glow=smoothstep(0.30,0.0,d)*0.32;
    vec3 ec=mix(vec3(1.0,0.55,0.18),vec3(0.24,0.7,1.0),aCool);
    ec=mix(ec,vec3(1.0,0.72,0.36),aDawn);
    col+=ec*on*(core+glow)*(0.5+0.6*pulse)*0.95;
  }

  // --- ACTO I · SOL (P 0 .. 0.26) ---
  float rise=smoothstep(0.0,0.24,P);
  vec2 suv=uv-vec2(0.16,mix(0.02,1.15,rise));
  float R=mix(0.36,0.11,rise);
  float spin=P*1.4+t*0.2;
  float sunGate=smoothstep(0.28,0.0,P);
  col+=sunColor(suv,R,spin,t)*sunGate;

  // --- ACTO II · captación: rayos de luz ámbar bajando del sol (P 0.10 .. 0.36) ---
  float g2=smoothstep(0.10,0.20,P)*smoothstep(0.40,0.26,P);
  if(g2>0.001){
    vec2 o=uv-vec2(0.16,1.05);          // origen donde quedó el sol
    float ang=atan(o.x,-o.y);           // abanico hacia abajo
    float fan=0.0;
    fan+=smoothstep(0.05,0.0,abs(fract(ang*3.0+0.5)-0.5));
    float rr=length(o);
    float ray=fan*smoothstep(2.2,0.2,rr)*(0.6+0.4*fbm(vec2(ang*6.0,rr*3.0-t*1.4)));
    col+=vec3(1.0,0.62,0.2)*ray*g2*0.5;
  }

  // --- ACTO III · transmisión: ríos de energía (ámbar→cian) (P 0.28 .. 0.56) ---
  float g3=smoothstep(0.26,0.38,P)*smoothstep(0.60,0.44,P);
  if(g3>0.001){
    vec3 estream=vec3(0.0);
    for(int i=0;i<5;i++){
      float fi=float(i);
      float cx=(-0.9)+fi*0.45+0.18*sin(t*0.5+fi);
      float warp=0.10*sin(uv.y*3.0+t*1.6+fi*1.7);
      float b=beam(uv,cx+warp,0.018,fi*2.3,t*2.2+fi);
      // partícula viajando por el rayo
      float flow=fract(uv.y*0.5 - t*0.5 + fi*0.2);
      b*=0.5+0.9*smoothstep(0.0,0.15,flow)*smoothstep(0.5,0.15,flow);
      estream+=mix(vec3(1.0,0.6,0.2),vec3(0.25,0.7,1.0),smoothstep(-0.2,0.2,P-0.34))*b;
    }
    col+=estream*g3*1.35;
  }

  // --- ACTOS IV–VI · horizonte + luces de ciudad encendiéndose (P 0.48 .. 0.92) ---
  float g4=smoothstep(0.46,0.58,P);
  if(g4>0.001){
    float hY=-0.18;                      // línea de horizonte (en uv)
    float horizon=smoothstep(0.02,0.0,abs(uv.y-hY))*0.6;
    col+=vec3(0.9,0.55,0.25)*horizon*g4*0.5;
    // resplandor del suelo
    col+=vec3(0.6,0.35,0.18)*smoothstep(hY,-0.7,uv.y)*g4*0.25;
    // luces (ventanas) sobre el horizonte
    float lit=smoothstep(0.5,0.92,P);    // cuántas encendidas
    for(int i=0;i<14;i++){
      float fi=float(i);
      float lx=(-1.3)+fi*0.19+0.02*sin(fi*7.0);
      float h=hash(vec2(fi,3.0));
      float ly=hY+0.015+h*0.05;
      vec2 lp=uv-vec2(lx,ly);
      float on=step(h, lit);            // se encienden progresivamente
      float tw=0.7+0.3*sin(t*2.0+fi);
      float core=smoothstep(0.012,0.0,length(lp));
      float glow=smoothstep(0.07,0.0,length(lp))*0.4;
      vec3 wc=mix(vec3(1.0,0.7,0.3),vec3(1.0,0.85,0.55),h);
      col+=wc*on*tw*(core+glow)*g4;
    }
    // red: líneas conectando (P 0.74+)
    float g6=smoothstep(0.74,0.84,P);
    float net=smoothstep(0.004,0.0,abs(uv.y-(hY+0.01)))*(0.5+0.5*sin(uv.x*20.0-t*2.0));
    col+=vec3(0.3,0.7,1.0)*net*g6*0.25;
  }

  // --- ACTO VII · amanecer cálido subiendo (P 0.86 .. 1.0) ---
  float g7=smoothstep(0.86,1.0,P);
  if(g7>0.001){
    float glow=smoothstep(-0.5,0.3,uv.y)*smoothstep(0.6,-0.2,uv.y);
    col+=mix(vec3(1.0,0.55,0.2),vec3(0.5,0.9,0.55),0.25)*glow*g7*0.35;
    col+=vec3(1.0,0.8,0.5)*smoothstep(0.02,0.0,abs(uv.y+0.18))*g7*0.4;
  }

  // vignette suave para legibilidad del contenido
  float vig=smoothstep(1.4,0.4,length(uv*vec2(0.8,1.0)));
  col*=0.74+0.26*vig;

  col=pow(max(col,0.0),vec3(0.86));
  gl_FragColor=vec4(col,1.0);
}`;
      const sh = (type, src) => { const o = gl.createShader(type); gl.shaderSource(o, src); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) console.warn('story shader', gl.getShaderInfoLog(o)); return o; };
      const prog = gl.createProgram();
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, vsSrc));
      gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fsSrc));
      gl.linkProgram(prog); gl.useProgram(prog);
      const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      const uRes = gl.getUniformLocation(prog, 'uRes'), uTime = gl.getUniformLocation(prog, 'uTime'), uProg = gl.getUniformLocation(prog, 'uProg'), uReduce = gl.getUniformLocation(prog, 'uReduce');
      const small = window.innerWidth < 760;
      const scale = small ? 0.6 : 1.0;
      const dpr = Math.min(window.devicePixelRatio || 1, small ? 1.0 : 1.5) * scale;
      const resize = () => { const w = window.innerWidth, h = window.innerHeight; cv.width = Math.max(1, Math.round(w * dpr)); cv.height = Math.max(1, Math.round(h * dpr)); gl.viewport(0, 0, cv.width, cv.height); };
      resize(); window.addEventListener('resize', resize);
      this._story = { p: 0, target: 0 };
      const readProg = () => { const d = document.documentElement; const max = d.scrollHeight - d.clientHeight; this._story.target = max > 0 ? d.scrollTop / max : 0; };
      window.addEventListener('scroll', readProg, { passive: true }); readProg();
      const t0 = performance.now();
      const frame = () => {
        const st = this._story;
        st.p += (st.target - st.p) * 0.08;
        const tt = (performance.now() - t0) / 1000;
        gl.uniform2f(uRes, cv.width, cv.height);
        gl.uniform1f(uTime, this.reduce ? 4.0 : tt);
        gl.uniform1f(uProg, st.p);
        gl.uniform1f(uReduce, this.reduce ? 1.0 : 0.0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    },

    // ---------- red eléctrica con pulsos (stats) ----------
    setupGrid() {
      const sec = document.getElementById('sss-stats');
      const cv = document.getElementById('sss-grid-fx');
      if (!sec || !cv) return;
      const ctx = cv.getContext('2d');
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      let W = 0, H = 0, nodes = [], edges = [];
      const A = 'rgba(255,180,61,';

      const build = () => {
        W = sec.clientWidth; H = sec.offsetHeight;
        cv.width = Math.max(1, W * dpr); cv.height = Math.max(1, H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const gap = 92;
        const cols = Math.max(4, Math.round(W / gap)) + 1;
        const rows = Math.max(2, Math.round(H / gap)) + 1;
        const cw = W / (cols - 1), ch = H / (rows - 1);
        nodes = []; edges = [];
        const idx = (c, r) => r * cols + c;
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
          nodes.push({ x: c * cw + (Math.random() - 0.5) * cw * 0.42, y: r * ch + (Math.random() - 0.5) * ch * 0.42, nb: [], glow: 0 });
        }
        const addEdge = (a, b) => { edges.push([a, b]); nodes[a].nb.push(b); nodes[b].nb.push(a); };
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
          if (c < cols - 1) addEdge(idx(c, r), idx(c + 1, r));
          if (r < rows - 1) addEdge(idx(c, r), idx(c, r + 1));
          if (c < cols - 1 && r < rows - 1 && Math.random() < 0.32) addEdge(idx(c, r), idx(c + 1, r + 1));
        }
      };
      build();
      window.addEventListener('resize', build);
      if (window.ResizeObserver) { try { new ResizeObserver(build).observe(sec); } catch (_) {} }

      const nextNb = (cur, prev) => {
        const nb = nodes[cur].nb;
        if (!nb.length) return cur;
        const opts = nb.filter(n => n !== prev);
        const pool = opts.length ? opts : nb;
        return pool[(Math.random() * pool.length) | 0];
      };
      const mkPulse = () => { const from = (Math.random() * nodes.length) | 0; return { prev: from, from, to: nextNb(from, -1), t: 0, sp: 0.012 + Math.random() * 0.02 }; };
      const NP = this.reduce ? 0 : 16;
      const pulses = []; for (let i = 0; i < NP; i++) { const p = mkPulse(); p.t = Math.random(); pulses.push(p); }

      const drawStatic = () => {
        ctx.lineWidth = 1;
        ctx.strokeStyle = A + '0.07)';
        ctx.beginPath();
        for (const e of edges) { const a = nodes[e[0]], b = nodes[e[1]]; ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); }
        ctx.stroke();
        for (const n of nodes) { ctx.fillStyle = A + '0.14)'; ctx.beginPath(); ctx.arc(n.x, n.y, 1.4, 0, 6.2832); ctx.fill(); }
      };

      if (this.reduce) { ctx.clearRect(0, 0, W, H); drawStatic(); return; }

      const step = () => {
        ctx.clearRect(0, 0, W, H);
        drawStatic();
        ctx.globalCompositeOperation = 'lighter';
        for (const p of pulses) {
          const a = nodes[p.from], b = nodes[p.to];
          const lg = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
          lg.addColorStop(Math.max(0, p.t - 0.4), A + '0)');
          lg.addColorStop(p.t, A + '0.55)');
          lg.addColorStop(Math.min(1, p.t + 0.02), A + '0)');
          ctx.strokeStyle = lg; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          const hx = a.x + (b.x - a.x) * p.t, hy = a.y + (b.y - a.y) * p.t;
          const rg = ctx.createRadialGradient(hx, hy, 0, hx, hy, 9);
          rg.addColorStop(0, 'rgba(255,231,180,0.95)'); rg.addColorStop(0.5, A + '0.5)'); rg.addColorStop(1, A + '0)');
          ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(hx, hy, 9, 0, 6.2832); ctx.fill();
          p.t += p.sp;
          if (p.t >= 1) { nodes[p.to].glow = 1; const nx = nextNb(p.to, p.from); p.prev = p.from; p.from = p.to; p.to = nx; p.t = 0; }
        }
        for (const n of nodes) {
          if (n.glow > 0.01) {
            const rg = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, 7 * n.glow + 2);
            rg.addColorStop(0, 'rgba(255,222,160,' + (0.85 * n.glow) + ')'); rg.addColorStop(1, A + '0)');
            ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(n.x, n.y, 7 * n.glow + 2, 0, 6.2832); ctx.fill();
            n.glow *= 0.94;
          }
        }
        ctx.globalCompositeOperation = 'source-over';
        this._gridRaf = requestAnimationFrame(step);
      };
      step();
    },

    // ---------- form ----------
    handleHeroSubmit(e) {
      e.preventDefault();
      const fb = document.getElementById('sss-hero-fb');
      if (fb) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(61,220,132,.12)';
        fb.style.color = '#7ee2a8';
        fb.style.border = '1px solid rgba(61,220,132,.3)';
        fb.textContent = '✅ ¡Solicitud enviada! Te llamamos en breve.';
      }
      e.target.reset();
    },

    // ---------- chat ----------
    initChat() {
      this.box = document.getElementById('sss-chat-msgs');
      if (!this.box) return;
      let saved = null;
      try { saved = localStorage.getItem('sss_chat_v2'); } catch (_) {}
      if (saved) this.box.innerHTML = saved;
      else this.bubble('¡Hola! Soy el asistente virtual del equipo comercial de Solsureste Solar. Puedo responder tus dudas técnicas y agendar una cita. ¿En qué ciudad te gustaría instalar las placas?', 'bot');
      this.scrollChat();
    },

    bubble(text, who) {
      if (!this.box) return;
      const d = document.createElement('div');
      if (who === 'user') {
        d.style.cssText = 'align-self:flex-end;max-width:82%;background:linear-gradient(135deg,#FFB43D,#F5921E);color:#1a1205;padding:9px 14px;border-radius:16px 16px 4px 16px;font-size:14px;line-height:1.45;font-weight:500';
      } else {
        d.style.cssText = 'align-self:flex-start;max-width:82%;background:rgba(255,255,255,.06);color:#f4f3f0;padding:9px 14px;border-radius:16px 16px 16px 4px;font-size:14px;line-height:1.45;border:1px solid rgba(255,255,255,.06)';
      }
      d.innerHTML = text;
      this.box.appendChild(d);
      this.scrollChat();
      this.saveChat();
    },

    scrollChat() { if (this.box) this.box.scrollTo({ top: this.box.scrollHeight, behavior: 'smooth' }); },
    saveChat() { try { localStorage.setItem('sss_chat_v2', this.box.innerHTML); } catch (_) {} },

    typing() {
      const t = document.createElement('div');
      t.id = 'sss-typing';
      t.style.cssText = 'align-self:flex-start;display:flex;gap:4px;padding:11px 14px;background:rgba(255,255,255,.06);border-radius:16px 16px 16px 4px;border:1px solid rgba(255,255,255,.06)';
      t.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:#FFB43D;animation:sssTyping 1.2s infinite"></span><span style="width:6px;height:6px;border-radius:50%;background:#FFB43D;animation:sssTyping 1.2s .2s infinite"></span><span style="width:6px;height:6px;border-radius:50%;background:#FFB43D;animation:sssTyping 1.2s .4s infinite"></span>';
      this.box.appendChild(t);
      this.scrollChat();
    },

    reply(msg) {
      const m = msg.toLowerCase();
      if (/(precio|cuesta|cuánto|cuanto|coste|presupuesto)/.test(m)) return 'El presupuesto exacto lo da tu comercial asignado tras una breve llamada y, si procede, una visita técnica. El estudio inicial es <strong>siempre gratuito</strong> y sin compromiso. ¿Te agendo esa llamada?';
      if (/(zona|murcia|alicante|lorca|cartagena|dónde|donde)/.test(m)) return '¡Perfecto! Trabajamos en toda la Región de Murcia y la provincia de Alicante con equipo y maquinaria propios. ¿Es una vivienda, una nave o un huerto solar?';
      if (/(batería|bateria|acumula)/.test(m)) return 'Podemos incluir baterías para maximizar tu autoconsumo nocturno. Lo dimensionamos en el estudio según tu curva de consumo real. ¿Quieres que un técnico lo valore?';
      if (/(financ|pagar|cuota|iva)/.test(m)) return 'Financiamos el 100% de la instalación, IVA incluido, a 10 años. En muchos casos la cuota es menor que el ahorro mensual, así ahorras desde el primer mes. ¿Te paso un ejemplo según tu factura?';
      if (/(garantía|garantia|años|mantenimiento)/.test(m)) return 'Ofrecemos garantía de 25 años en rendimiento de módulos y de mano de obra, además de soporte post-venta y monitorización. ¿Quieres agendar tu estudio?';
      if (/(cita|llamada|agend|contact|estudio|gratis|gratuito)/.test(m)) return '¡Genial! Déjanos tu nombre y teléfono en el formulario de la izquierda o dime tu ciudad y un técnico te llamará hoy mismo. ☀️';
      return 'Gracias por tu mensaje. Para darte cifras fiables, lo ideal es un estudio gratuito a partir de tu factura. ¿En qué ciudad estás y qué tipo de instalación te interesa (vivienda, nave o huerto solar)?';
    },

    handleChatSubmit(e) {
      e.preventDefault();
      const input = document.getElementById('sss-chat-input');
      const msg = (input.value || '').trim();
      if (!msg) return;
      this.bubble(msg.replace(/</g, '&lt;'), 'user');
      input.value = '';
      this.typing();
      const delay = 700 + Math.random() * 700;
      setTimeout(() => {
        const t = document.getElementById('sss-typing');
        if (t) t.remove();
        this.bubble(this.reply(msg), 'bot');
      }, delay);
    },

    resetChat() {
      try { localStorage.removeItem('sss_chat_v2'); } catch (_) {}
      if (this.box) this.box.innerHTML = '';
      this.bubble('¡Hola de nuevo! ¿En qué ciudad te gustaría instalar las placas y qué tipo de instalación necesitas?', 'bot');
    },

    // ---------- i18n ----------
    setLang(lang) {
      const en = {
        'nav.services': 'Services', 'nav.projects': 'Projects', 'nav.resources': 'Process', 'nav.faq': 'FAQ',
        'nav.contact': 'Contact', 'nav.cta': 'Book a call',
        'hero.h1': 'We install solar panels across Murcia and Alicante, ',
        'hero.p': 'Solar panels for homes and businesses, plus solar-farm development. With our own machinery and crews we execute every project without relying on third parties.',
        'form.title': 'Request your free study',
        'value.h2': 'Stop overpaying your electricity bill',
        'tech.label': 'Our technical proposal', 'tech.h2': 'The most rigorous solar design in the southeast',
        'cases.h2': 'Real examples of completed installations',
        'why.h2': 'Why choose Solsureste Solar for your solar installation',
        'test.h2': 'What our clients say',
        'fin.h2': 'We finance 100% of your installation, even the VAT',
        'proc.h2': 'What to expect when you request a study from Solsureste Solar',
        'faq.h2': 'Got questions about solar installation?',
        'footer.copy': '© 2026 Solsureste Solar · Paco Alcaraz. All rights reserved.',
      };
      document.querySelectorAll('[data-i18n]').forEach(el => {
        const k = el.getAttribute('data-i18n');
        if (!el.dataset.es) el.dataset.es = el.innerHTML;
        if (lang === 'en' && en[k]) {
          if (k === 'hero.h1') el.innerHTML = en[k] + '<span class="sss-shimmer">start to finish</span>';
          else el.textContent = en[k];
        } else {
          el.innerHTML = el.dataset.es;
        }
      });
      const es = document.getElementById('sss-lang-es'), enb = document.getElementById('sss-lang-en');
      if (es && enb) {
        es.classList.toggle('sss-langbtn-on', lang === 'es');
        es.classList.toggle('sss-langbtn-off', lang !== 'es');
        enb.classList.toggle('sss-langbtn-on', lang === 'en');
        enb.classList.toggle('sss-langbtn-off', lang !== 'en');
      }
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => S.init());
  } else {
    S.init();
  }
})();
