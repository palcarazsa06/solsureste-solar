/* Panel de contenido de la web.
 *
 * Convive con admin.js (leads) dentro de /admin: comparte la credencial guardada en
 * sessionStorage por el login y la misma regla que el resto de esta página — cero JS
 * inline y cero atributos onclick, porque la CSP del servidor (script-src 'self', sin
 * unsafe-inline) los descarta sin dar ningún error visible.
 *
 * Todo se hace con delegación de eventos sobre el contenedor, igual que la tabla de leads.
 */

let cmsCampos = [];
let cmsGrupos = [];
let cmsIdioma = 'es';
let cmsCargado = false;

function cmsCredencial() {
    return sessionStorage.getItem('credencialAdmin');
}

async function cmsFetch(url, opciones) {
    const config = Object.assign({ headers: {} }, opciones || {});
    config.headers = Object.assign({ 'Authorization': cmsCredencial() }, config.headers);
    const respuesta = await fetch(url, config);
    if (respuesta.status === 401) {
        cmsAviso('La sesión ha caducado. Vuelve a entrar.', 'error');
        throw new Error('no autorizado');
    }
    return respuesta;
}

function cmsAviso(mensaje, tipo) {
    const el = document.getElementById('cms-aviso');
    el.textContent = mensaje;
    el.className = 'cms-aviso ' + tipo;
    if (!mensaje) el.classList.add('hidden');
}

// Misma transformación que cms_blog.slugificar en el servidor, para que la dirección que se
// ve al escribir el título sea la que se va a guardar de verdad.
function cmsSlugificar(titulo) {
    return titulo
        .normalize('NFKD').replace(/[̀-ͯ]/g, '')
        .replace(/[^a-zA-Z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .toLowerCase()
        .slice(0, 90);
}

function esc(texto) {
    return String(texto == null ? '' : texto)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// --- Carga y pintado ---

async function cmsCargar() {
    try {
        const respuesta = await cmsFetch('/api/cms/campos?idioma=' + cmsIdioma);
        if (!respuesta.ok) { cmsAviso('No se pudo cargar el contenido.', 'error'); return; }
        const datos = await respuesta.json();
        cmsCampos = datos.campos;
        cmsGrupos = datos.grupos;
        cmsPintar();
        cmsAviso('', '');
    } catch (e) {
        // cmsFetch ya avisó si fue un 401; aquí solo se evita dejar la vista a medias.
    }
}

function cmsPintar() {
    let html = '';
    cmsGrupos.forEach((grupo) => {
        const campos = cmsCampos.filter((c) => c.grupo === grupo.id);
        if (!campos.length) return;
        html += '<div class="cms-grupo"><header><h3>' + esc(grupo.nombre) + '</h3>' +
                '<p>' + esc(grupo.descripcion) + '</p></header>';
        campos.forEach((campo) => { html += cmsPintarCampo(campo); });
        html += '</div>';
    });
    document.getElementById('cms-campos').innerHTML = html;
}

function cmsPintarCampo(campo) {
    let html = '<div class="cms-campo" data-clave="' + esc(campo.clave) + '">';

    html += '<div class="cms-campo-cab"><label for="f-' + esc(campo.clave) + '">' + esc(campo.etiqueta) + '</label>';
    if (campo.revisar) {
        html += '<span class="cms-badge">Traducción automática · revisar</span>';
    } else if (campo.modificado) {
        html += '<span class="cms-badge modificado">Modificado</span>';
    }
    html += '</div>';

    if (campo.ayuda) html += '<p class="ayuda">' + esc(campo.ayuda) + '</p>';

    if (campo.tipo === 'tabla') {
        html += cmsPintarTabla(campo);
    } else if (campo.tipo === 'texto_largo') {
        html += '<p class="ayuda">Puedes poner algo <strong>en negrita</strong> escribiéndolo entre dos asteriscos: **así**.</p>';
        html += '<textarea id="f-' + esc(campo.clave) + '" data-input>' + esc(campo.valor) + '</textarea>';
    } else {
        html += '<input type="text" id="f-' + esc(campo.clave) + '" data-input value="' + esc(campo.valor) + '">';
    }

    html += '<div class="cms-acciones">';
    html += '<button class="cms-btn cms-btn-guardar" data-accion="guardar">Guardar</button>';
    if (campo.tipo === 'tabla') {
        html += '<button class="cms-btn" data-accion="anadir-fila">+ Añadir fila</button>';
    }
    html += '<button class="cms-btn" data-accion="historial">Ver cambios anteriores</button>';
    if (campo.modificado) {
        html += '<button class="cms-btn" data-accion="restaurar">Restaurar original</button>';
    }
    if (campo.tipo !== 'tabla') {
        html += '<span class="cms-contador" data-contador>' + String(campo.valor).length +
                ' / ' + campo.max_length + '</span>';
    }
    html += '<span class="cms-estado" data-estado></span>';
    html += '</div><div class="cms-historial hidden" data-historial></div></div>';
    return html;
}

function cmsPintarTabla(campo) {
    let html = '<div class="cms-tabla-scroll"><table class="cms-tabla" data-tabla><thead><tr>';
    campo.columnas.forEach((col) => { html += '<th>' + esc(col) + '</th>'; });
    html += '<th></th></tr></thead><tbody>';
    campo.valor.forEach((fila) => { html += cmsFilaTabla(fila); });
    html += '</tbody></table></div>';
    return html;
}

function cmsFilaTabla(fila) {
    let html = '<tr>';
    fila.forEach((celda) => {
        html += '<td><input type="text" data-celda value="' + esc(celda) + '"></td>';
    });
    html += '<td><button class="cms-btn-fila" data-accion="borrar-fila" title="Quitar esta fila">✕</button></td></tr>';
    return html;
}

// --- Lectura del valor que hay ahora en pantalla ---

function cmsLeerValor(contenedor, campo) {
    if (campo.tipo === 'tabla') {
        const filas = [];
        contenedor.querySelectorAll('[data-tabla] tbody tr').forEach((tr) => {
            filas.push(Array.from(tr.querySelectorAll('[data-celda]')).map((i) => i.value));
        });
        return filas;
    }
    return contenedor.querySelector('[data-input]').value;
}

function cmsDefinicion(clave) {
    return cmsCampos.find((c) => c.clave === clave);
}

function cmsEstado(contenedor, mensaje, tipo) {
    const el = contenedor.querySelector('[data-estado]');
    el.textContent = mensaje;
    el.className = 'cms-estado ' + (tipo || '');
    if (tipo === 'ok') setTimeout(() => { el.textContent = ''; }, 2500);
}

// --- Acciones ---

async function cmsGuardar(contenedor, clave) {
    const campo = cmsDefinicion(clave);
    const valor = cmsLeerValor(contenedor, campo);
    cmsEstado(contenedor, 'Guardando…', '');

    const respuesta = await cmsFetch('/api/cms/contenido', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clave: clave, idioma: cmsIdioma, valor: valor }),
    });
    const datos = await respuesta.json();

    if (!respuesta.ok) {
        // El servidor manda el motivo ya redactado en castellano: se muestra tal cual.
        cmsEstado(contenedor, datos.detail || 'No se pudo guardar.', 'error');
        return;
    }
    campo.valor = valor;
    campo.modificado = true;
    campo.revisar = false;
    cmsRefrescarCabecera(contenedor, campo);

    // Al guardar en español se traduce sola la web inglesa. Se dice siempre qué ha pasado
    // con esa parte: si falla, quien edita tiene que saber que el inglés se ha quedado atrás.
    if (cmsIdioma === 'es' && datos.traduccion) {
        const fallo = datos.valor_en === null || datos.valor_en === undefined;
        cmsEstado(contenedor, '✓ Publicado. ' + datos.traduccion, fallo ? 'error' : 'ok');
        cmsBotonReintentar(contenedor, fallo && campo.tipo !== 'tabla');
    } else {
        cmsEstado(contenedor, '✓ Publicado en la web', 'ok');
    }
}

function cmsBotonReintentar(contenedor, mostrar) {
    const existente = contenedor.querySelector('[data-accion="traducir"]');
    if (!mostrar) { if (existente) existente.remove(); return; }
    if (existente) return;
    const boton = document.createElement('button');
    boton.className = 'cms-btn';
    boton.dataset.accion = 'traducir';
    boton.textContent = 'Reintentar traducción';
    contenedor.querySelector('.cms-acciones').insertBefore(
        boton, contenedor.querySelector('[data-estado]'));
}

async function cmsTraducir(contenedor, clave) {
    cmsEstado(contenedor, 'Traduciendo…', '');
    const respuesta = await cmsFetch('/api/cms/contenido/' + encodeURIComponent(clave) + '/traducir',
                                     { method: 'POST' });
    const datos = await respuesta.json();
    if (!respuesta.ok) {
        cmsEstado(contenedor, datos.detail || 'No se pudo traducir.', 'error');
        return;
    }
    cmsEstado(contenedor, '✓ ' + datos.traduccion, 'ok');
    cmsBotonReintentar(contenedor, false);
}

function cmsRefrescarCabecera(contenedor, campo) {
    const cabecera = contenedor.querySelector('.cms-campo-cab');
    const badge = cabecera.querySelector('.cms-badge');
    if (badge) badge.remove();
    if (campo.modificado) {
        const nuevo = document.createElement('span');
        nuevo.className = 'cms-badge modificado';
        nuevo.textContent = 'Modificado';
        cabecera.appendChild(nuevo);
    }
    if (!contenedor.querySelector('[data-accion="restaurar"]')) {
        const boton = document.createElement('button');
        boton.className = 'cms-btn';
        boton.dataset.accion = 'restaurar';
        boton.textContent = 'Restaurar original';
        contenedor.querySelector('.cms-acciones').insertBefore(
            boton, contenedor.querySelector('[data-contador]') || contenedor.querySelector('[data-estado]'));
    }
}

async function cmsRestaurar(contenedor, clave) {
    const campo = cmsDefinicion(clave);
    if (!confirm('Se va a recuperar el texto original de «' + campo.etiqueta + '».\n\n¿Seguro?')) return;

    const respuesta = await cmsFetch('/api/cms/contenido/' + encodeURIComponent(clave) +
                                     '/restaurar?idioma=' + cmsIdioma, { method: 'POST' });
    if (!respuesta.ok) { cmsEstado(contenedor, 'No se pudo restaurar.', 'error'); return; }
    await cmsCargar();
}

async function cmsHistorial(contenedor, clave) {
    const caja = contenedor.querySelector('[data-historial]');
    if (!caja.classList.contains('hidden')) { caja.classList.add('hidden'); return; }

    const respuesta = await cmsFetch('/api/cms/contenido/' + encodeURIComponent(clave) +
                                     '/historial?idioma=' + cmsIdioma);
    if (!respuesta.ok) return;
    const datos = await respuesta.json();

    if (!datos.versiones.length) {
        caja.innerHTML = '<div class="cms-historial-item"><span>Todavía no se ha cambiado nunca.</span></div>';
    } else {
        caja.innerHTML = datos.versiones.map((v) => {
            const texto = typeof v.valor === 'string' ? v.valor : '(tabla con ' + v.valor.length + ' filas)';
            return '<div class="cms-historial-item"><span>' + esc(texto) + '</span>' +
                   '<time>' + esc(v.creado_en) + '</time>' +
                   '<button class="cms-btn" data-accion="recuperar" data-version="' + v.id + '">Poner este</button></div>';
        }).join('');
    }
    caja.classList.remove('hidden');
}

function cmsRecuperarVersion(contenedor, clave, versionId) {
    const caja = contenedor.querySelector('[data-historial]');
    const item = caja.querySelector('[data-version="' + versionId + '"]').closest('.cms-historial-item');
    const texto = item.querySelector('span').textContent;
    const entrada = contenedor.querySelector('[data-input]');
    if (!entrada) { alert('Las tablas se recuperan editando las celdas a mano.'); return; }
    entrada.value = texto;
    cmsActualizarContador(contenedor);
    cmsEstado(contenedor, 'Texto recuperado — pulsa Guardar para publicarlo.', '');
}

function cmsActualizarContador(contenedor) {
    const contador = contenedor.querySelector('[data-contador]');
    const entrada = contenedor.querySelector('[data-input]');
    if (!contador || !entrada) return;
    const campo = cmsDefinicion(contenedor.dataset.clave);
    contador.textContent = entrada.value.length + ' / ' + campo.max_length;
    contador.classList.toggle('pasado', entrada.value.length > campo.max_length);
}

// --- Preguntas frecuentes ---
// Comparten página con el resto del panel pero tienen su propio modelo (una lista que se
// puede reordenar), así que van por separado en vez de forzarlas al esquema de campos.

let faqCargada = false;

async function faqCargar() {
    const respuesta = await cmsFetch('/api/cms/faq');
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    faqPintar(datos.preguntas);
}

function faqPintar(preguntas) {
    document.getElementById('faq-lista').innerHTML = preguntas.map((p, i) => {
        const inactiva = p.activa ? '' : ' <span class="cms-badge">Oculta en la web</span>';
        return '<div class="cms-grupo" data-faq="' + p.id + '"><div class="cms-campo">' +
            '<div class="cms-campo-cab"><label>Pregunta ' + (i + 1) + inactiva + '</label></div>' +
            '<input type="text" data-pregunta value="' + esc(p.pregunta) + '">' +
            '<div class="ayuda" style="margin:.5rem 0 .25rem">Respuesta</div>' +
            '<textarea data-respuesta>' + esc(p.respuesta) + '</textarea>' +
            '<div class="cms-acciones">' +
            '<button class="cms-btn cms-btn-guardar" data-accion="faq-guardar">Guardar</button>' +
            '<button class="cms-btn" data-accion="faq-subir"' + (i === 0 ? ' disabled' : '') + '>↑ Subir</button>' +
            '<button class="cms-btn" data-accion="faq-bajar"' + (i === preguntas.length - 1 ? ' disabled' : '') + '>↓ Bajar</button>' +
            '<button class="cms-btn" data-accion="faq-visibilidad">' + (p.activa ? 'Ocultar' : 'Mostrar') + '</button>' +
            '<button class="cms-btn" data-accion="faq-borrar">Eliminar</button>' +
            '<span class="cms-estado" data-estado></span>' +
            '</div></div></div>';
    }).join('');
}

async function faqGuardar(caja) {
    const cuerpo = {
        pregunta: caja.querySelector('[data-pregunta]').value,
        respuesta: caja.querySelector('[data-respuesta]').value,
    };
    const respuesta = await cmsFetch('/api/cms/faq/' + caja.dataset.faq, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
    });
    const datos = await respuesta.json();
    const campo = caja.querySelector('.cms-campo');
    if (!respuesta.ok) { cmsEstado(campo, datos.detail || 'No se pudo guardar.', 'error'); return; }
    cmsEstado(campo, '✓ Publicado en la web', 'ok');
}

async function faqPatch(id, parametros) {
    await cmsFetch('/api/cms/faq/' + id + '?' + parametros, { method: 'PATCH' });
    await faqCargar();
}

async function faqMover(caja, direccion) {
    // Se intercambia el `orden` con el vecino: es lo mínimo que hace falta para reordenar
    // sin renumerar la lista entera en cada movimiento.
    const cajas = Array.from(document.querySelectorAll('[data-faq]'));
    const i = cajas.indexOf(caja);
    const vecino = cajas[i + direccion];
    if (!vecino) return;
    await cmsFetch('/api/cms/faq/' + caja.dataset.faq + '?orden=' + (i + direccion), { method: 'PATCH' });
    await cmsFetch('/api/cms/faq/' + vecino.dataset.faq + '?orden=' + i, { method: 'PATCH' });
    await faqCargar();
}

async function faqBorrar(caja) {
    const pregunta = caja.querySelector('[data-pregunta]').value;
    if (!confirm('Se va a eliminar «' + pregunta + '» de la página de preguntas frecuentes.\n\n¿Seguro?')) return;
    const respuesta = await cmsFetch('/api/cms/faq/' + caja.dataset.faq, { method: 'DELETE' });
    if (!respuesta.ok) {
        const datos = await respuesta.json();
        alert(datos.detail || 'No se pudo eliminar.');
        return;
    }
    await faqCargar();
}

async function faqNueva() {
    const respuesta = await cmsFetch('/api/cms/faq', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: 'Pregunta nueva', respuesta: 'Escribe aquí la respuesta.' }),
    });
    if (!respuesta.ok) { alert('No se pudo añadir la pregunta.'); return; }
    await faqCargar();
    const cajas = document.querySelectorAll('[data-faq]');
    cajas[cajas.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// --- Blog ---

let blogCargado = false;
let blogQuill = null;
let blogIdActual = null;      // null = artículo nuevo, todavía sin guardar
let blogSlugTocado = false;   // si lo han editado a mano, deja de generarse desde el título

function blogAviso(mensaje, tipo) {
    const el = document.getElementById('blog-aviso');
    el.textContent = mensaje;
    el.className = 'cms-aviso ' + tipo + (mensaje ? '' : ' hidden');
}

function blogEstado(mensaje, tipo) {
    const el = document.getElementById('blog-estado');
    el.textContent = mensaje;
    el.className = 'cms-estado ' + (tipo || '');
    if (tipo === 'ok') setTimeout(() => { el.textContent = ''; }, 3000);
}

function blogIniciarEditor() {
    if (blogQuill) return;
    // Barra recortada a propósito: sin colores, tamaños ni fuentes. Solo se ofrece lo que
    // el saneador del servidor deja pasar, así nadie escribe algo que luego desaparece.
    blogQuill = new Quill('#blog-editor-quill', {
        theme: 'snow',
        placeholder: 'Escribe aquí el artículo…',
        modules: {
            toolbar: [
                [{ header: [2, 3, false] }],
                ['bold', 'italic'],
                [{ list: 'ordered' }, { list: 'bullet' }],
                ['blockquote', 'link', 'image'],
                ['clean'],
            ],
        },
    });

    // Al pegar una imagen o subirla desde la barra, Quill la metería como data: URI dentro
    // del HTML (el saneador la tiraría). Se sube al servidor y se inserta su URL.
    blogQuill.getModule('toolbar').addHandler('image', () => {
        const selector = document.createElement('input');
        selector.type = 'file';
        selector.accept = 'image/jpeg,image/png,image/gif,image/webp';
        selector.onchange = async () => {
            const archivo = selector.files[0];
            if (!archivo) return;
            blogEstado('Subiendo imagen…', '');
            const cuerpo = new FormData();
            cuerpo.append('archivo', archivo);
            const respuesta = await cmsFetch('/api/cms/imagenes', { method: 'POST', body: cuerpo });
            const datos = await respuesta.json();
            if (!respuesta.ok) { blogEstado(datos.detail || 'No se pudo subir.', 'error'); return; }
            const rango = blogQuill.getSelection(true);
            blogQuill.insertEmbed(rango.index, 'image', datos.url, 'user');
            blogEstado('✓ Imagen insertada', 'ok');
        };
        selector.click();
    });
}

async function blogCargar() {
    const respuesta = await cmsFetch('/api/cms/articulos');
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    blogPintarLista(datos.articulos);
}

function blogPintarLista(articulos) {
    document.getElementById('blog-editor').classList.add('hidden');
    document.getElementById('blog-lista').classList.remove('hidden');

    if (!articulos.length) {
        document.getElementById('blog-lista').innerHTML =
            '<p style="color:#6b7280;font-size:.9rem">Todavía no hay artículos. Pulsa «Escribir artículo».</p>';
        return;
    }
    document.getElementById('blog-lista').innerHTML = '<div class="cms-grupo">' + articulos.map((a) => {
        const badge = a.publicado
            ? '<span class="cms-badge badge-publicado">Publicado</span>'
            : '<span class="cms-badge badge-borrador">Borrador</span>';
        return '<div class="blog-fila" data-articulo="' + a.id + '">' +
            '<span class="titulo">' + esc(a.titulo) + '</span>' + badge +
            '<span class="fecha">' + esc(a.fecha_legible || '—') + '</span>' +
            '<button class="cms-btn" data-accion="blog-editar">Editar</button>' +
            '<button class="cms-btn" data-accion="blog-borrar">Eliminar</button>' +
            '</div>';
    }).join('') + '</div>';
}

function blogAbrirEditor(articulo) {
    blogIniciarEditor();
    blogIdActual = articulo ? articulo.id : null;
    blogSlugTocado = Boolean(articulo);

    document.getElementById('blog-f-titulo').value = articulo ? articulo.titulo : '';
    document.getElementById('blog-f-slug').value = articulo ? articulo.slug : '';
    document.getElementById('blog-f-meta').value = articulo ? articulo.meta_description : '';
    document.getElementById('blog-f-eyebrow').value = articulo ? articulo.eyebrow : '';
    document.getElementById('blog-f-portada').value = articulo ? articulo.imagen_portada : '';
    document.getElementById('blog-f-alt').value = articulo ? articulo.alt_portada : '';
    document.getElementById('blog-f-pie').value = articulo ? articulo.pie_portada : '';
    blogQuill.root.innerHTML = articulo ? articulo.cuerpo_html : '';

    document.getElementById('blog-titulo-vista').textContent = articulo ? 'Editar artículo' : 'Artículo nuevo';
    document.getElementById('blog-publicar').textContent =
        articulo && articulo.publicado ? 'Guardar y republicar' : 'Publicar en la web';
    document.getElementById('blog-previsualizar').classList.toggle('hidden', !articulo);

    document.getElementById('blog-lista').classList.add('hidden');
    document.getElementById('blog-editor').classList.remove('hidden');
    blogActualizarContadores();
    blogEstado('', '');
}

function blogActualizarContadores() {
    const titulo = document.getElementById('blog-f-titulo').value;
    const meta = document.getElementById('blog-f-meta').value;

    document.getElementById('blog-c-titulo').textContent = titulo.length + ' / 140';
    const cMeta = document.getElementById('blog-c-meta');
    cMeta.textContent = meta.length + ' / 160 recomendados';
    // Pasado ese punto Google recorta la descripción en los resultados. Es un aviso, no un
    // error: el límite duro (200) lo aplica el servidor.
    cMeta.classList.toggle('pasado', meta.length > 160);

    document.getElementById('blog-slug-vista').textContent =
        document.getElementById('blog-f-slug').value || '…';
}

function blogRecoger(publicado) {
    return {
        titulo: document.getElementById('blog-f-titulo').value,
        slug: document.getElementById('blog-f-slug').value,
        meta_description: document.getElementById('blog-f-meta').value,
        eyebrow: document.getElementById('blog-f-eyebrow').value,
        imagen_portada: document.getElementById('blog-f-portada').value,
        alt_portada: document.getElementById('blog-f-alt').value,
        pie_portada: document.getElementById('blog-f-pie').value,
        cuerpo_html: blogQuill.root.innerHTML,
        publicado: publicado,
    };
}

async function blogGuardar(publicado) {
    const datos = blogRecoger(publicado);

    // Cambiar la dirección de un artículo ya publicado rompe la URL que Google tiene
    // indexada. Se avisa y se pide confirmación; el servidor deja un 301 desde la antigua.
    if (blogIdActual !== null && publicado) {
        const original = document.getElementById('blog-f-slug').dataset.original;
        if (original && original !== datos.slug) {
            const seguir = confirm(
                'Vas a cambiar la dirección del artículo:\n\n' + original + '\n→ ' + datos.slug +
                '\n\nLa dirección antigua se quedará redirigiendo a la nueva, pero puede que ' +
                'Google tarde un tiempo en actualizarse.\n\n¿Continuar?');
            if (!seguir) return;
        }
    }

    blogEstado('Guardando…', '');
    const url = blogIdActual === null ? '/api/cms/articulos' : '/api/cms/articulos/' + blogIdActual;
    const respuesta = await cmsFetch(url, {
        method: blogIdActual === null ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(datos),
    });
    const cuerpo = await respuesta.json();

    if (!respuesta.ok) { blogEstado(cuerpo.detail || 'No se pudo guardar.', 'error'); return; }
    if (blogIdActual === null) blogIdActual = cuerpo.id;
    document.getElementById('blog-f-slug').value = cuerpo.slug;
    document.getElementById('blog-f-slug').dataset.original = cuerpo.slug;
    blogEstado(publicado ? '✓ Publicado en la web' : '✓ Borrador guardado', 'ok');
    document.getElementById('blog-previsualizar').classList.remove('hidden');
}

async function blogBorrar(fila) {
    const titulo = fila.querySelector('.titulo').textContent;
    if (!confirm('Se va a eliminar «' + titulo + '» para siempre.\n\nSi estaba publicado, su dirección dejará de funcionar.\n\n¿Seguro?')) return;
    const respuesta = await cmsFetch('/api/cms/articulos/' + fila.dataset.articulo, { method: 'DELETE' });
    if (!respuesta.ok) { blogAviso('No se pudo eliminar.', 'error'); return; }
    await blogCargar();
}

async function blogEditar(fila) {
    const respuesta = await cmsFetch('/api/cms/articulos/' + fila.dataset.articulo);
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    blogAbrirEditor(datos.articulo);
    document.getElementById('blog-f-slug').dataset.original = datos.articulo.slug;
}

// --- Imágenes ---

let imgCargada = false;

function imgAviso(mensaje, tipo) {
    const el = document.getElementById('img-aviso');
    el.textContent = mensaje;
    el.className = 'cms-aviso ' + tipo + (mensaje ? '' : ' hidden');
}

async function imgCargar() {
    const respuesta = await cmsFetch('/api/cms/imagenes');
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    imgPintar(datos.imagenes);
}

function imgPintar(imagenes) {
    const galeria = document.getElementById('img-galeria');
    if (!imagenes.length) {
        galeria.innerHTML = '<p style="color:#6b7280;font-size:.9rem">Todavía no has subido ninguna imagen.</p>';
        return;
    }
    galeria.innerHTML = imagenes.map((im) => {
        const kb = Math.round(im.bytes / 1024);
        return '<div class="img-tarjeta" data-imagen="' + esc(im.nombre_fichero) + '">' +
            '<img src="' + esc(im.url) + '" alt="' + esc(im.nombre_original) + '" loading="lazy">' +
            '<div class="img-datos"><p class="nombre">' + esc(im.nombre_original) + '</p>' +
            '<p>' + im.ancho + '×' + im.alto + ' · ' + kb + ' KB</p></div>' +
            '<div class="img-acciones">' +
            '<button class="cms-btn" data-accion="img-copiar" data-url="' + esc(im.url) + '">Copiar enlace</button>' +
            '<button class="cms-btn" data-accion="img-borrar">Eliminar</button>' +
            '</div></div>';
    }).join('');
}

async function imgSubir(archivo) {
    if (!archivo) return;
    imgAviso('Subiendo «' + archivo.name + '»…', 'ok');

    const cuerpo = new FormData();
    cuerpo.append('archivo', archivo);
    // Sin Content-Type a mano: el navegador tiene que poner el boundary del multipart.
    const respuesta = await cmsFetch('/api/cms/imagenes', { method: 'POST', body: cuerpo });
    const datos = await respuesta.json();

    if (!respuesta.ok) { imgAviso(datos.detail || 'No se pudo subir la imagen.', 'error'); return; }
    imgAviso('✓ Imagen subida y optimizada (' + Math.round(datos.bytes / 1024) + ' KB).', 'ok');
    await imgCargar();
}

async function imgBorrar(tarjeta) {
    const nombre = tarjeta.dataset.imagen;
    if (!confirm('Se va a eliminar esta imagen para siempre.\n\nSi está puesta en alguna página, ahí dejará de verse.\n\n¿Seguro?')) return;
    const respuesta = await cmsFetch('/api/cms/imagenes/' + encodeURIComponent(nombre), { method: 'DELETE' });
    if (!respuesta.ok) { imgAviso('No se pudo eliminar.', 'error'); return; }
    await imgCargar();
}

function imgCopiar(url) {
    const completa = window.location.origin + url;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(completa).then(
            () => imgAviso('✓ Enlace copiado: ' + completa, 'ok'),
            () => imgAviso('Copia el enlace a mano: ' + completa, 'ok'));
    } else {
        imgAviso('Copia el enlace a mano: ' + completa, 'ok');
    }
}

// --- Eventos (delegación: los botones se crean dinámicamente) ---

function cmsIniciar() {
    const contenedor = document.getElementById('cms-campos');
    if (!contenedor) return;

    contenedor.addEventListener('click', (e) => {
        const boton = e.target.closest('button[data-accion]');
        if (!boton) return;
        const campo = boton.closest('.cms-campo');
        const clave = campo.dataset.clave;
        const accion = boton.dataset.accion;

        if (accion === 'guardar') cmsGuardar(campo, clave);
        else if (accion === 'traducir') cmsTraducir(campo, clave);
        else if (accion === 'restaurar') cmsRestaurar(campo, clave);
        else if (accion === 'historial') cmsHistorial(campo, clave);
        else if (accion === 'recuperar') cmsRecuperarVersion(campo, clave, boton.dataset.version);
        else if (accion === 'borrar-fila') {
            const cuerpo = boton.closest('tbody');
            if (cuerpo.rows.length <= 1) { alert('La tabla necesita al menos una fila.'); return; }
            boton.closest('tr').remove();
        } else if (accion === 'anadir-fila') {
            const definicion = cmsDefinicion(clave);
            const cuerpo = campo.querySelector('[data-tabla] tbody');
            cuerpo.insertAdjacentHTML('beforeend', cmsFilaTabla(definicion.columnas.map(() => '')));
        }
    });

    contenedor.addEventListener('input', (e) => {
        if (e.target.matches('[data-input]')) cmsActualizarContador(e.target.closest('.cms-campo'));
    });

    document.getElementById('cms-idioma').addEventListener('change', (e) => {
        cmsIdioma = e.target.value;
        cmsCargar();
    });

    document.getElementById('faq-lista').addEventListener('click', (e) => {
        const boton = e.target.closest('button[data-accion]');
        if (!boton) return;
        const caja = boton.closest('[data-faq]');
        const accion = boton.dataset.accion;

        if (accion === 'faq-guardar') faqGuardar(caja);
        else if (accion === 'faq-subir') faqMover(caja, -1);
        else if (accion === 'faq-bajar') faqMover(caja, 1);
        else if (accion === 'faq-borrar') faqBorrar(caja);
        else if (accion === 'faq-visibilidad') {
            const oculta = boton.textContent.trim() === 'Ocultar';
            faqPatch(caja.dataset.faq, 'activa=' + (oculta ? 'false' : 'true'));
        }
    });

    document.getElementById('faq-nueva').addEventListener('click', faqNueva);

    document.getElementById('blog-lista').addEventListener('click', (e) => {
        const boton = e.target.closest('button[data-accion]');
        if (!boton) return;
        const fila = boton.closest('[data-articulo]');
        if (boton.dataset.accion === 'blog-editar') blogEditar(fila);
        else if (boton.dataset.accion === 'blog-borrar') blogBorrar(fila);
    });

    document.getElementById('blog-nuevo').addEventListener('click', () => blogAbrirEditor(null));
    document.getElementById('blog-guardar').addEventListener('click', () => blogGuardar(false));
    document.getElementById('blog-publicar').addEventListener('click', () => blogGuardar(true));
    document.getElementById('blog-cancelar').addEventListener('click', () => {
        document.getElementById('blog-titulo-vista').textContent = 'Artículos del blog';
        blogCargar();
    });
    document.getElementById('blog-previsualizar').addEventListener('click', () => {
        if (blogIdActual === null) { blogEstado('Guarda el artículo primero.', 'error'); return; }
        window.open('/admin/preview/blog/' + blogIdActual, '_blank');
    });

    document.getElementById('blog-f-titulo').addEventListener('input', (e) => {
        // La dirección se genera desde el título mientras nadie la haya tocado a mano.
        if (!blogSlugTocado) {
            document.getElementById('blog-f-slug').value = cmsSlugificar(e.target.value);
        }
        blogActualizarContadores();
    });
    document.getElementById('blog-f-slug').addEventListener('input', () => {
        blogSlugTocado = true;
        blogActualizarContadores();
    });
    document.getElementById('blog-f-meta').addEventListener('input', blogActualizarContadores);

    document.getElementById('img-archivo').addEventListener('change', (e) => {
        imgSubir(e.target.files[0]);
        e.target.value = '';  // permite volver a elegir el mismo archivo
    });

    document.getElementById('img-galeria').addEventListener('click', (e) => {
        const boton = e.target.closest('button[data-accion]');
        if (!boton) return;
        if (boton.dataset.accion === 'img-borrar') imgBorrar(boton.closest('[data-imagen]'));
        else if (boton.dataset.accion === 'img-copiar') imgCopiar(boton.dataset.url);
    });

    document.getElementById('tabs').addEventListener('click', (e) => {
        const pestana = e.target.closest('.tab');
        if (!pestana) return;
        const vista = pestana.dataset.vista;

        document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('is-active', t === pestana));
        ['leads', 'contenido', 'faq', 'blog', 'imagenes'].forEach((v) => {
            document.getElementById('vista-' + v).classList.toggle('hidden', v !== vista);
        });

        // Cada pestaña se carga la primera vez que se entra, no al abrir el panel: quien
        // solo mira leads no paga esas peticiones.
        if (vista === 'contenido' && !cmsCargado) { cmsCargado = true; cmsCargar(); }
        if (vista === 'faq' && !faqCargada) { faqCargada = true; faqCargar(); }
        if (vista === 'blog' && !blogCargado) { blogCargado = true; blogCargar(); }
        if (vista === 'imagenes' && !imgCargada) { imgCargada = true; imgCargar(); }
    });
}

cmsIniciar();
