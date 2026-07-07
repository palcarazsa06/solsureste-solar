let radarInterval;
let todosLosLeads = [];

async function iniciarSesion() {
    const usu = document.getElementById('username').value;
    const pas = document.getElementById('password').value;
    const credencial = 'Basic ' + btoa(usu + ':' + pas);

    try {
        const respuesta = await fetch('/api/leads', { headers: { 'Authorization': credencial } });
        if (!respuesta.ok) { alert('❌ Usuario o contraseña incorrectos.'); return; }

        sessionStorage.setItem('credencialAdmin', credencial);
        document.getElementById('login-screen').classList.add('hidden');
        document.getElementById('dashboard-screen').classList.remove('hidden');

        await cargarDatosBD();
        radarInterval = setInterval(cargarDatosBD, 10000);
    } catch (error) {
        alert('❌ No se pudo conectar con el servidor.');
    }
}

function cerrarSesion() {
    sessionStorage.removeItem('credencialAdmin');
    document.getElementById('dashboard-screen').classList.add('hidden');
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('password').value = '';
    clearInterval(radarInterval);
}

async function cargarDatosBD() {
    const credencial = sessionStorage.getItem('credencialAdmin');
    try {
        const respuesta = await fetch('/api/leads', { headers: { 'Authorization': credencial } });
        if (respuesta.status === 401) { clearInterval(radarInterval); cerrarSesion(); return; }

        const json = await respuesta.json();
        todosLosLeads = json.data || [];
        window._costeHistorico = json.coste_historico || 0;

        actualizarStats();
        renderTabla();
    } catch (error) {
        console.error("Error al cargar los datos:", error);
    }
}

function actualizarStats() {
    const total = todosLosLeads.length;
    const enProceso = todosLosLeads.filter(c => c.estado === 'CUALIFICADOR' || c.estado === 'AGENDADOR').length;
    const gestionados = todosLosLeads.filter(c => c.gestionado).length;
    const costeTotal = (window._costeHistorico || 0) + todosLosLeads.reduce((sum, c) => sum + (c.coste_usd || 0), 0);

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-en-proceso').textContent = enProceso;
    document.getElementById('stat-gestionados').textContent = gestionados;
    document.getElementById('stat-coste').textContent = '$' + costeTotal.toFixed(4);
}

function normalizarTexto(s) {
    return (s || '').toString().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function escapeHtml(str) {
    return (str || '').toString().replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttr(str) {
    return (str || '').toString().replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderTabla() {
    const tbody = document.getElementById('tabla-clientes');
    const textoBusqueda = normalizarTexto(document.getElementById('buscador').value.trim());
    const filtroEstado = document.getElementById('filtroEstado').value;

    let leads = todosLosLeads;

    if (filtroEstado === '__GESTIONADOS__') {
        leads = leads.filter(c => c.gestionado);
    } else if (filtroEstado) {
        leads = leads.filter(c => c.estado === filtroEstado);
    }

    if (textoBusqueda) {
        leads = leads.filter(c =>
            normalizarTexto(c.nombre).includes(textoBusqueda) ||
            normalizarTexto(c.correo).includes(textoBusqueda) ||
            normalizarTexto(c.telefono).includes(textoBusqueda) ||
            normalizarTexto(c.ciudad).includes(textoBusqueda)
        );
    }

    if (leads.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="2">No hay leads que coincidan con los filtros.</td></tr>';
        return;
    }

    let html = '';
    leads.forEach(cliente => {
        const cNombre   = escapeHtml((cliente.nombre   && cliente.nombre   !== 'Desconocido' && cliente.nombre   !== '') ? cliente.nombre   : '👤 En proceso...');
        const cTelefono = escapeHtml((cliente.telefono && cliente.telefono !== 'Desconocido' && cliente.telefono !== '') ? cliente.telefono : 'Sin teléfono');
        const cCorreo   = escapeHtml((cliente.correo   && cliente.correo   !== 'Desconocido' && cliente.correo   !== '') ? cliente.correo   : 'Sin correo');
        const cCiudad   = escapeHtml((cliente.ciudad   && cliente.ciudad   !== 'Desconocido' && cliente.ciudad   !== '') ? cliente.ciudad   : 'Sin ciudad');
        const cEstado   = cliente.estado || 'INICIO';
        const gestionado = cliente.gestionado;

        const tokensTotal = (cliente.tokens_prompt || 0) + (cliente.tokens_completion || 0);
        const coste = cliente.coste_usd || 0;
        const costeStr = tokensTotal > 0 ? `${tokensTotal.toLocaleString()} tokens · $${coste.toFixed(4)}` : '';

        const createdAt = cliente.created_at ? cliente.created_at.substring(0, 16).replace('T', ' ') : '';

        let badgeClase = "badge-default";
        if (cEstado === "CUALIFICADOR")  badgeClase = "badge-cualificador";
        if (cEstado === "AGENDADOR")     badgeClase = "badge-agendador";
        if (cEstado === "TERMINAR")      badgeClase = "badge-terminar";
        if (cEstado === "LEAD_DIRECTO")  badgeClase = "badge-lead-directo";

        const gestionadoBadge = gestionado
            ? `<span class="badge badge-gestionado">✓ Gestionado</span>`
            : '';

        // Solo se muestra si ya se capturó algún dato de contacto: para un chat recién
        // empezado (sin teléfono ni correo) el estado de CRM aún no es relevante.
        const tieneDatosContacto = cTelefono !== 'Sin teléfono' || cCorreo !== 'Sin correo';
        const crmBadge = !tieneDatosContacto
            ? ''
            : cliente.crm_enviado
                ? `<span class="badge badge-crm-ok">📤 CRM enviado</span>`
                : `<span class="badge badge-crm-pendiente" title="Dato inválido o webhook caído: revisar y reenviar a mano">⚠ CRM no enviado</span>`;

        const gestionadoBtnLabel = gestionado ? '↩ Desmarcar' : '✓ Gestionado';
        const gestionadoBtnClase = gestionado ? 'btn-desmarcar' : 'btn-marcar';

        const uid = escapeAttr(cliente.user_id);

        html += `
        <tr class="${gestionado ? 'gestionado' : ''}">
            <td class="col-cliente">
                <div>
                    <div class="lead-name">${cNombre}</div>
                    <div class="lead-id" title="ID de Sesión">${cliente.user_id}</div>
                    ${createdAt ? `<div class="lead-created">🕐 ${createdAt}</div>` : ''}
                </div>

                <div class="lead-info">
                    <div class="lead-info-row"><span>📞</span><span>${cTelefono}</span></div>
                    <div class="lead-info-row"><span>📧</span><span>${cCorreo}</span></div>
                    <div class="lead-info-row"><span>📍</span><span>${cCiudad}</span></div>
                    ${costeStr ? `<div class="lead-info-row cost"><span>💰</span><span>${costeStr}</span></div>` : ''}
                </div>

                <div class="badges-row">
                    <span class="badge ${badgeClase}">${cEstado}</span>
                    ${gestionadoBadge}
                    ${crmBadge}
                </div>

                <div class="actions-row">
                    <button
                        data-action="toggle" data-uid="${uid}"
                        class="btn-action ${gestionadoBtnClase}">
                        ${gestionadoBtnLabel}
                    </button>
                    <button
                        data-action="eliminar" data-uid="${uid}"
                        class="btn-action btn-eliminar">
                        🗑 Eliminar
                    </button>
                </div>
            </td>
            <td>
                <div class="chat-panel">`;

        if (cliente.historial && Array.isArray(cliente.historial)) {
            let mensajesUtiles = 0;
            cliente.historial.forEach(msg => {
                if (!msg.content || msg.role === 'system' || msg.role === 'tool') return;
                mensajesUtiles++;
                const contenido = String(msg.content).replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
                if (msg.role === 'user') {
                    html += `<div class="chat-bubble chat-user">
                        <strong>👤 Cliente:</strong>${contenido}</div>`;
                } else if (msg.role === 'assistant') {
                    html += `<div class="chat-bubble chat-assistant">
                        <strong>🤖 IA:</strong>${contenido}</div>`;
                }
            });
            if (mensajesUtiles === 0) html += '<p class="chat-empty">Conversación en blanco.</p>';
        } else {
            html += '<p class="chat-empty">No hay historial legible.</p>';
        }

        html += `</div></td></tr>`;
    });

    tbody.innerHTML = html;
}

async function toggleGestionado(userId) {
    const credencial = sessionStorage.getItem('credencialAdmin');
    try {
        const res = await fetch(`/api/leads/${encodeURIComponent(userId)}/gestionado`, {
            method: 'PATCH',
            headers: { 'Authorization': credencial }
        });
        if (!res.ok) throw new Error('Error ' + res.status);
        await cargarDatosBD();
    } catch (e) {
        alert('No se pudo actualizar el estado. Intenta de nuevo.');
    }
}

async function eliminarLead(userId) {
    if (!confirm(`¿Eliminar este lead permanentemente?\n\nEsta acción no se puede deshacer.`)) return;
    const credencial = sessionStorage.getItem('credencialAdmin');
    try {
        const res = await fetch(`/api/leads/${encodeURIComponent(userId)}`, {
            method: 'DELETE',
            headers: { 'Authorization': credencial }
        });
        if (!res.ok) throw new Error('Error ' + res.status);
        await cargarDatosBD();
    } catch (e) {
        alert('No se pudo eliminar el lead. Intenta de nuevo.');
    }
}

document.getElementById('password').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') iniciarSesion();
});
document.querySelector('#login-screen .btn-entrar').addEventListener('click', iniciarSesion);
document.querySelector('.btn-logout').addEventListener('click', cerrarSesion);
document.querySelector('.btn-refresh').addEventListener('click', cargarDatosBD);
document.getElementById('buscador').addEventListener('input', renderTabla);
document.getElementById('filtroEstado').addEventListener('change', renderTabla);
document.getElementById('tabla-clientes').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const uid = btn.dataset.uid;
    if (btn.dataset.action === 'toggle') toggleGestionado(uid);
    else if (btn.dataset.action === 'eliminar') eliminarLead(uid);
});
