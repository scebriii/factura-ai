// ═══════════════════════════════════════════════════════════════════════════
// FacturaAI v2 — Frontend Logic
// ═══════════════════════════════════════════════════════════════════════════

// ─── DOM Refs ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const dom = {
    apiKey:      $('api-key-input'),
    toggleKey:   $('toggle-key'),
    dropZone:    $('drop-zone'),
    fileInput:   $('file-input'),
    filePill:    $('file-pill'),
    fileName:    $('file-pill-name'),
    fileSize:    $('file-pill-size'),
    fileRemove:  $('file-remove'),
    btnAnalyze:  $('btn-analyze'),
    loading:     $('loading-bar'),
    resultCard:  $('result-card'),
    resultGrid:  $('result-grid'),
    toasts:      $('toast-container'),
    tableBody:   $('table-body'),
    emptyState:  $('empty-state'),
    search:      $('search-input'),
    btnExport:   $('btn-export'),
    btnRefresh:  $('btn-refresh'),
    deleteDialog:$('delete-dialog'),
    dialogText:  $('dialog-text'),
    dialogCancel:$('dialog-cancel'),
    dialogConfirm:$('dialog-confirm'),
    kpiTotal:    $('kpi-total'),
    kpiImporte:  $('kpi-importe'),
    kpiMedia:    $('kpi-media'),
    kpiProveedores:$('kpi-proveedores'),
};

// ─── State ─────────────────────────────────────────────────────────────────
let selectedFile = null;
let allInvoices = [];
let chartMensual = null;
let chartProveedores = null;
let pendingDeleteId = null;

// ─── API Key persistence ──────────────────────────────────────────────────
function getApiKey() { return dom.apiKey.value.trim(); }

function loadApiKey() {
    const saved = localStorage.getItem('fai_key');
    if (saved) dom.apiKey.value = saved;
}

dom.apiKey.addEventListener('input', () => {
    localStorage.setItem('fai_key', dom.apiKey.value);
});

dom.toggleKey.addEventListener('click', () => {
    dom.apiKey.type = dom.apiKey.type === 'password' ? 'text' : 'password';
});

loadApiKey();

// ─── Helpers ───────────────────────────────────────────────────────────────
function formatBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
}

function formatDate(iso) {
    if (!iso) return '\u2014';
    return new Date(iso).toLocaleDateString('es-ES', {
        day: '2-digit', month: '2-digit', year: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

function formatCurrency(n) {
    if (n === null || n === undefined) return '\u2014';
    return new Intl.NumberFormat('es-ES', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(n);
}

function formatMonthLabel(ym) {
    if (!ym) return '';
    const [y, m] = ym.split('-');
    const months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    return months[parseInt(m) - 1] + ' ' + y.slice(2);
}

// ─── Toast Notifications ──────────────────────────────────────────────────
function showToast(message, type = 'ok') {
    const toast = document.createElement('div');
    toast.className = `toast is-${type}`;
    toast.textContent = message;
    dom.toasts.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('is-leaving');
        toast.addEventListener('animationend', () => toast.remove());
    }, 3000);
}

// ─── Fetch wrapper ─────────────────────────────────────────────────────────
async function apiFetch(url, options = {}) {
    const key = getApiKey();
    if (!key) {
        showToast('Introduce tu API Key', 'error');
        throw new Error('No API Key');
    }

    const headers = { 'X-API-Key': key, ...(options.headers || {}) };
    const res = await fetch(url, { ...options, headers });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error del servidor' }));
        throw new Error(err.detail || `Error ${res.status}`);
    }
    return res.json();
}

// ─── Drag & Drop ───────────────────────────────────────────────────────────
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
    dom.dropZone.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); });
});

dom.dropZone.addEventListener('dragenter', () => dom.dropZone.classList.add('is-over'));
dom.dropZone.addEventListener('dragover', () => dom.dropZone.classList.add('is-over'));
dom.dropZone.addEventListener('dragleave', () => dom.dropZone.classList.remove('is-over'));

dom.dropZone.addEventListener('drop', e => {
    dom.dropZone.classList.remove('is-over');
    if (e.dataTransfer.files.length) selectFile(e.dataTransfer.files[0]);
});

dom.dropZone.addEventListener('click', () => dom.fileInput.click());
dom.dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') dom.fileInput.click(); });
dom.fileInput.addEventListener('change', () => { if (dom.fileInput.files.length) selectFile(dom.fileInput.files[0]); });
dom.fileRemove.addEventListener('click', e => { e.stopPropagation(); clearFile(); });

function selectFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Solo se aceptan archivos PDF', 'error');
        return;
    }
    selectedFile = file;
    dom.fileName.textContent = file.name;
    dom.fileSize.textContent = formatBytes(file.size);
    dom.filePill.hidden = false;
    dom.dropZone.classList.add('has-file');
    dom.btnAnalyze.disabled = false;
    dom.resultCard.hidden = true;
}

function clearFile() {
    selectedFile = null;
    dom.fileInput.value = '';
    dom.filePill.hidden = true;
    dom.dropZone.classList.remove('has-file');
    dom.btnAnalyze.disabled = true;
}

// ─── Analyze Invoice ───────────────────────────────────────────────────────
dom.btnAnalyze.addEventListener('click', analyzeInvoice);

async function analyzeInvoice() {
    if (!selectedFile) return;

    dom.loading.hidden = false;
    dom.resultCard.hidden = true;
    dom.btnAnalyze.disabled = true;

    try {
        const form = new FormData();
        form.append('archivo', selectedFile);

        const result = await apiFetch('/extraer-factura', { method: 'POST', body: form });

        renderResult(result.datos);
        showToast('Factura analizada correctamente');
        clearFile();
        loadDashboard();

    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        dom.loading.hidden = true;
        dom.btnAnalyze.disabled = !selectedFile;
    }
}

// ─── Render Result ─────────────────────────────────────────────────────────
function renderResult(data) {
    dom.resultGrid.innerHTML = '';

    const fields = [
        { key: 'proveedor', label: 'Proveedor' },
        { key: 'cif_nif', label: 'CIF / NIF' },
        { key: 'numero_factura', label: 'N. Factura' },
        { key: 'fecha', label: 'Fecha' },
        { key: 'importe_total', label: 'Importe Total', highlight: true },
        { key: 'moneda', label: 'Moneda' },
    ];

    fields.forEach(f => {
        const val = data[f.key];
        const el = document.createElement('div');
        el.className = 'result-item';
        el.innerHTML = `
            <p class="result-label">${f.label}</p>
            <p class="result-value ${f.highlight ? 'is-highlight' : ''}">${val ?? '\u2014'}</p>
        `;
        dom.resultGrid.appendChild(el);
    });

    if (data.conceptos && data.conceptos.length) {
        const el = document.createElement('div');
        el.className = 'result-item';
        el.style.gridColumn = '1 / -1';
        el.innerHTML = `
            <p class="result-label">Conceptos</p>
            <p class="result-value">${data.conceptos.join(', ')}</p>
        `;
        dom.resultGrid.appendChild(el);
    }

    dom.resultCard.hidden = false;
}

// ─── Dashboard (KPIs + Charts) ─────────────────────────────────────────────
async function loadDashboard() {
    try {
        const [stats, history] = await Promise.all([
            apiFetch('/estadisticas'),
            apiFetch('/facturas')
        ]);

        // KPIs
        dom.kpiTotal.textContent = stats.kpis.total_facturas;
        dom.kpiImporte.textContent = formatCurrency(stats.kpis.importe_total) + ' \u20AC';
        dom.kpiMedia.textContent = formatCurrency(stats.kpis.importe_medio) + ' \u20AC';
        dom.kpiProveedores.textContent = stats.kpis.proveedores_unicos;

        // Charts
        renderChartMensual(stats.gasto_mensual);
        renderChartProveedores(stats.top_proveedores);

        // Table
        allInvoices = history.facturas;
        renderTable(allInvoices);

    } catch (err) {
        // Silently fail on initial load if no API key yet
        if (getApiKey()) console.warn('Dashboard error:', err.message);
    }
}

// ─── Charts ────────────────────────────────────────────────────────────────
const chartColors = {
    accent: 'oklch(0.72 0.14 180)',
    accentDim: 'oklch(0.72 0.14 180 / 0.2)',
    grid: 'oklch(0.94 0 0 / 0.06)',
    text: 'oklch(0.50 0.015 260)',
};

function commonChartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
        },
    };
}

function renderChartMensual(data) {
    const ctx = document.getElementById('chart-mensual');
    if (!ctx) return;

    if (chartMensual) chartMensual.destroy();

    chartMensual = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => formatMonthLabel(d.mes)),
            datasets: [{
                data: data.map(d => d.total_mes),
                backgroundColor: chartColors.accentDim,
                borderColor: chartColors.accent,
                borderWidth: 1.5,
                borderRadius: 4,
                borderSkipped: false,
            }]
        },
        options: {
            ...commonChartOptions(),
            scales: {
                x: {
                    ticks: { color: chartColors.text, font: { size: 10, family: 'Inter' } },
                    grid: { display: false },
                    border: { display: false },
                },
                y: {
                    ticks: {
                        color: chartColors.text,
                        font: { size: 10, family: 'Inter' },
                        callback: v => formatCurrency(v)
                    },
                    grid: { color: chartColors.grid },
                    border: { display: false },
                }
            }
        }
    });
}

function renderChartProveedores(data) {
    const ctx = document.getElementById('chart-proveedores');
    if (!ctx) return;

    if (chartProveedores) chartProveedores.destroy();

    const palette = [
        'oklch(0.72 0.14 180)',
        'oklch(0.70 0.14 220)',
        'oklch(0.72 0.16 155)',
        'oklch(0.78 0.16 80)',
        'oklch(0.68 0.12 300)',
    ];

    chartProveedores = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.proveedor || 'Sin nombre'),
            datasets: [{
                data: data.map(d => d.total_gasto),
                backgroundColor: palette.slice(0, data.length),
                borderColor: 'oklch(0.16 0.012 260)',
                borderWidth: 2,
            }]
        },
        options: {
            ...commonChartOptions(),
            cutout: '65%',
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        color: chartColors.text,
                        font: { size: 10, family: 'Inter' },
                        padding: 12,
                        boxWidth: 10,
                        boxHeight: 10,
                        borderRadius: 2,
                        useBorderRadius: true,
                    }
                }
            }
        }
    });
}

// ─── History Table ─────────────────────────────────────────────────────────
function renderTable(invoices) {
    dom.tableBody.innerHTML = '';

    if (!invoices.length) {
        dom.emptyState.style.display = 'flex';
        return;
    }

    dom.emptyState.style.display = 'none';

    invoices.forEach(inv => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${inv.id}</td>
            <td>${inv.proveedor || '\u2014'}</td>
            <td>${inv.cif_nif || '\u2014'}</td>
            <td>${inv.numero_factura || '\u2014'}</td>
            <td>${inv.fecha_factura || '\u2014'}</td>
            <td class="td-amount">${inv.importe_total !== null ? formatCurrency(inv.importe_total) + ' ' + (inv.moneda || '') : '\u2014'}</td>
            <td>${formatDate(inv.procesado_en)}</td>
            <td>
                <button class="btn-delete-row" data-id="${inv.id}" title="Eliminar factura ${inv.id}" type="button">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </td>
        `;
        dom.tableBody.appendChild(tr);
    });

    // Attach delete handlers
    dom.tableBody.querySelectorAll('.btn-delete-row').forEach(btn => {
        btn.addEventListener('click', () => openDeleteDialog(parseInt(btn.dataset.id)));
    });
}

// ─── Search / Filter ───────────────────────────────────────────────────────
dom.search.addEventListener('input', () => {
    const q = dom.search.value.toLowerCase();
    if (!q) {
        renderTable(allInvoices);
        return;
    }
    const filtered = allInvoices.filter(inv =>
        (inv.proveedor || '').toLowerCase().includes(q) ||
        (inv.numero_factura || '').toLowerCase().includes(q) ||
        (inv.cif_nif || '').toLowerCase().includes(q)
    );
    renderTable(filtered);
});

// ─── Delete Invoice ────────────────────────────────────────────────────────
function openDeleteDialog(id) {
    pendingDeleteId = id;
    dom.dialogText.textContent = `Se eliminara la factura #${id}. Esta accion no se puede deshacer.`;
    dom.deleteDialog.showModal();
}

dom.dialogCancel.addEventListener('click', () => {
    pendingDeleteId = null;
    dom.deleteDialog.close();
});

dom.deleteDialog.addEventListener('click', e => {
    // Light dismiss: click on backdrop
    if (e.target === dom.deleteDialog) {
        pendingDeleteId = null;
        dom.deleteDialog.close();
    }
});

dom.dialogConfirm.addEventListener('click', async () => {
    if (pendingDeleteId === null) return;
    const id = pendingDeleteId;
    dom.deleteDialog.close();

    try {
        await apiFetch(`/facturas/${id}`, { method: 'DELETE' });
        showToast(`Factura #${id} eliminada`);
        loadDashboard();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        pendingDeleteId = null;
    }
});

// ─── Export CSV ─────────────────────────────────────────────────────────────
dom.btnExport.addEventListener('click', () => {
    if (!allInvoices.length) {
        showToast('No hay datos para exportar', 'error');
        return;
    }

    const headers = ['ID', 'Archivo', 'Proveedor', 'CIF_NIF', 'N_Factura', 'Fecha', 'Importe', 'Moneda', 'Conceptos', 'Procesado'];
    const rows = allInvoices.map(inv => [
        inv.id,
        inv.archivo_original || '',
        inv.proveedor || '',
        inv.cif_nif || '',
        inv.numero_factura || '',
        inv.fecha_factura || '',
        inv.importe_total || '',
        inv.moneda || '',
        Array.isArray(inv.conceptos) ? inv.conceptos.join('; ') : '',
        inv.procesado_en || ''
    ]);

    const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\n');

    // BOM for Excel UTF-8 compatibility
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `facturas_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('CSV descargado');
});

// ─── Refresh ───────────────────────────────────────────────────────────────
dom.btnRefresh.addEventListener('click', () => {
    dom.search.value = '';
    loadDashboard();
});

// ─── Health Check ──────────────────────────────────────────────────────────
async function checkHealth() {
    const pill = document.getElementById('status-pill');
    const dot = pill.querySelector('.status-dot');
    const label = pill.querySelector('.status-label');
    try {
        const res = await fetch('/salud', { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error('not ok');
        pill.classList.remove('is-offline');
        dot.style.animation = '';
        label.textContent = 'Online';
    } catch {
        pill.classList.add('is-offline');
        label.textContent = 'Offline';
    }
}

// ─── Init ──────────────────────────────────────────────────────────────────
checkHealth();
loadDashboard();
