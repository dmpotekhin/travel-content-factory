/* ── Travel Content Factory — Frontend App ───────────────── */
const API = {
    async get(url) { const r = await fetch(url); if (!r.ok) throw new Error(await r.text()); return r.json(); },
    async post(url, data) {
        const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (!r.ok) { const e = await r.text(); throw new Error(e); }
        return r.json();
    },
    async del(url) { const r = await fetch(url, { method: 'DELETE' }); if (!r.ok) throw new Error(await r.text()); return r.json(); },
};

// ── State ──────────────────────────────────────────────────
const state = {
    tab: 'archive',
    archivePage: 1,
    filters: { media_type: '', country: '', year: '', hashtag: '' },
    selectedPlatform: 'reels',
};

// ── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initFilters();
    initProjectModal();
    initFactory();
    loadMedia();
    loadProjects();
    loadFilterOptions();
});

// ── Tabs ───────────────────────────────────────────────────
function initTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            state.tab = tab.dataset.tab;
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
            document.getElementById(`tab-${state.tab}`).classList.add('active');
            if (state.tab === 'projects') loadProjects();
        });
    });
}

// ── Toast ──────────────────────────────────────────────────
function toast(msg, type = 'info') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast ${type}`;
    setTimeout(() => el.classList.add('hidden'), 3000);
}

// ── Filters ────────────────────────────────────────────────
function initFilters() {
    ['filter-type', 'filter-country', 'filter-year'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            state.filters.media_type = document.getElementById('filter-type').value;
            state.filters.country = document.getElementById('filter-country').value;
            state.filters.year = document.getElementById('filter-year').value;
            state.archivePage = 1;
            loadMedia();
        });
    });
    document.getElementById('filter-hashtag').addEventListener('input', debounce(() => {
        state.filters.hashtag = document.getElementById('filter-hashtag').value;
        state.archivePage = 1;
        loadMedia();
    }, 400));

    document.getElementById('btn-scan').addEventListener('click', scanFolder);
}

async function loadFilterOptions() {
    try {
        const countries = await API.get('/api/media/countries');
        const years = await API.get('/api/media/years');
        populateSelect('filter-country', countries);
        populateSelect('filter-year', years);
    } catch (e) { /* ignore */ }
}

function populateSelect(id, items) {
    const sel = document.getElementById(id);
    const current = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    items.forEach(v => { const o = document.createElement('option'); o.value = v; o.textContent = v; sel.appendChild(o); });
    if (current) sel.value = current;
}

function debounce(fn, ms) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); }; }

// ── Media Grid ─────────────────────────────────────────────
async function loadMedia() {
    const grid = document.getElementById('media-grid');
    grid.innerHTML = '<div class="empty-state">Loading...</div>';

    const params = new URLSearchParams();
    if (state.filters.media_type) params.set('media_type', state.filters.media_type);
    if (state.filters.country) params.set('country', state.filters.country);
    if (state.filters.year) params.set('year', state.filters.year);
    if (state.filters.hashtag) params.set('hashtag', state.filters.hashtag);
    params.set('page', state.archivePage);
    params.set('page_size', '50');

    try {
        const data = await API.get(`/api/media/list?${params}`);
        if (!data.items.length) {
            grid.innerHTML = '<div class="empty-state">No media found.</div>';
        } else {
            grid.innerHTML = data.items.map(m => `
                <div class="media-card" data-id="${m.id}">
                    <img src="/api/media/${m.id}/thumbnail" alt="${esc(m.filename)}" loading="lazy"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22140%22><rect fill=%22%23111%22 width=%22200%22 height=%22140%22/><text fill=%22%23666%22 x=%22100%22 y=%2275%22 text-anchor=%22middle%22 font-size=%2212%22>No preview</text></svg>'">
                    <div class="card-body">
                        <div class="card-name">${esc(m.filename)}</div>
                        <div class="card-meta">
                            ${m.country ? `<span class="card-badge">${esc(m.country)}</span>` : ''}
                            ${m.date_taken ? `<span>${m.date_taken.slice(0,4)}</span>` : ''}
                            <span>${m.media_type}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        renderPagination(data.total);
    } catch (e) {
        grid.innerHTML = `<div class="empty-state">Error: ${esc(e.message)}</div>`;
        toast(e.message, 'error');
    }
}

function renderPagination(total) {
    const pages = Math.ceil(total / 50);
    const el = document.getElementById('pagination');
    if (pages <= 1) { el.innerHTML = ''; return; }
    let html = '';
    for (let i = 1; i <= Math.min(pages, 10); i++) {
        html += `<button class="${i === state.archivePage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    el.innerHTML = html;
    el.querySelectorAll('button').forEach(b => {
        b.addEventListener('click', () => { state.archivePage = parseInt(b.dataset.page); loadMedia(); });
    });
}

async function scanFolder() {
    const path = prompt('Enter folder path to scan:');
    if (!path) return;
    try {
        const r = await API.post('/api/media/scan', { path });
        toast(`Imported ${r.imported} files (${r.skipped} skipped)`, 'success');
        loadMedia();
        loadFilterOptions();
    } catch (e) { toast(e.message, 'error'); }
}

// ── Projects ───────────────────────────────────────────────
async function loadProjects() {
    const el = document.getElementById('projects-list');
    try {
        const data = await API.get('/api/projects/');
        if (!data.items.length) {
            el.innerHTML = '<div class="empty-state">No projects yet.</div>';
        } else {
            el.innerHTML = data.items.map(p => `
                <div class="project-card" data-id="${p.id}">
                    <div class="proj-info" onclick="showProjectDetail(${p.id})">
                        <div class="proj-name">${esc(p.name)}</div>
                        <div class="proj-meta">
                            ${p.mode} · ${p.platform || 'any'} · ${p.clip_count} clips · ${p.duration_target || '-'}s
                            <span class="status-badge status-${p.status}">${p.status}</span>
                        </div>
                    </div>
                    <div class="proj-actions">
                        ${p.status === 'ready' && p.export_path ? `<a href="/api/projects/${p.id}/download" class="btn btn-primary btn-sm" style="padding:4px 10px;font-size:0.75rem">Download</a>` : ''}
                        ${p.status === 'ready' ? `<button class="btn btn-secondary btn-sm" style="padding:4px 10px;font-size:0.75rem" onclick="renderProject(${p.id})">Render</button>` : ''}
                        ${p.status === 'draft' ? `<button class="btn btn-secondary btn-sm" style="padding:4px 10px;font-size:0.75rem" onclick="renderProject(${p.id})">Render</button>` : ''}
                        <button class="btn btn-danger btn-sm" style="padding:4px 10px;font-size:0.75rem" onclick="deleteProject(${p.id})">Del</button>
                    </div>
                </div>
            `).join('');
        }
    } catch (e) { toast(e.message, 'error'); }
}

async function renderProject(id) {
    try {
        toast('Rendering...', 'info');
        await API.post(`/api/projects/${id}/render`, {});
        toast('Render complete!', 'success');
        loadProjects();
    } catch (e) { toast(e.message, 'error'); }
}

async function deleteProject(id) {
    if (!confirm('Delete this project?')) return;
    try {
        await API.del(`/api/projects/${id}`);
        toast('Project deleted', 'success');
        loadProjects();
    } catch (e) { toast(e.message, 'error'); }
}

async function showProjectDetail(id) {
    try {
        const p = await API.get(`/api/projects/${id}`);
        document.getElementById('detail-content').innerHTML = `
            <div class="detail-header">
                <h2>${esc(p.name)}</h2>
                <div class="detail-meta">Mode: ${p.mode} · Platform: ${p.platform || 'any'} · Status: ${p.status} · Target: ${p.duration_target || '-'}s</div>
            </div>
            <div class="clip-list">
                ${p.clips.length ? p.clips.map((c, i) => `
                    <div class="clip-item">
                        <div class="clip-index">${i+1}</div>
                        <div class="clip-info">
                            <div class="clip-name">${c.media ? esc(c.media.filename) : '(no media)'}</div>
                            ${c.scene_description ? `<div class="clip-scene">${esc(c.scene_description)}</div>` : ''}
                        </div>
                        <div class="clip-duration">${c.start_time.toFixed(1)}s → ${c.duration.toFixed(1)}s</div>
                    </div>
                `).join('') : '<div class="empty-state">No clips in this project.</div>'}
            </div>
        `;
        document.getElementById('modal-detail').classList.remove('hidden');
    } catch (e) { toast(e.message, 'error'); }
}

// ── Project Modal ──────────────────────────────────────────
function initProjectModal() {
    document.getElementById('btn-new-project').addEventListener('click', () => {
        document.getElementById('modal-project').classList.remove('hidden');
        loadProjectFilterOptions();
    });
    document.getElementById('btn-create-project').addEventListener('click', createProject);
    document.getElementById('proj-mode').addEventListener('change', function() {
        document.getElementById('proj-script-group').classList.toggle('hidden', this.value !== 'script');
    });

    // Close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.add('hidden');
        });
    });
    // Click outside to close
    document.querySelectorAll('.modal').forEach(m => {
        m.addEventListener('click', (e) => { if (e.target === m) m.classList.add('hidden'); });
    });
}

async function loadProjectFilterOptions() {
    try {
        const countries = await API.get('/api/media/countries');
        const years = await API.get('/api/media/years');
        populateSelect('proj-country', countries);
        populateSelect('proj-year', years);
    } catch (e) { /* ignore */ }
}

async function createProject() {
    const data = {
        name: document.getElementById('proj-name').value || 'Untitled',
        mode: document.getElementById('proj-mode').value,
        platform: document.getElementById('proj-platform').value,
        duration_target: parseFloat(document.getElementById('proj-duration').value) || 30,
        script_text: document.getElementById('proj-script').value || null,
        country_filter: document.getElementById('proj-country').value || null,
        year_filter: document.getElementById('proj-year').value ? parseInt(document.getElementById('proj-year').value) : null,
    };
    try {
        const p = await API.post('/api/projects/', data);
        document.getElementById('modal-project').classList.add('hidden');
        toast(`Project "${p.name}" created!`, 'success');
        loadProjects();
        // Switch to projects tab
        document.querySelector('.nav-tab[data-tab="projects"]').click();
    } catch (e) { toast(e.message, 'error'); }
}

// ── Content Factory ────────────────────────────────────────
function initFactory() {
    document.querySelectorAll('.platform-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.platform-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.selectedPlatform = btn.dataset.platform;
        });
    });

    document.getElementById('btn-generate').addEventListener('click', generate);
}

async function generate() {
    const topic = document.getElementById('factory-topic').value.trim();
    if (!topic) { toast('Enter a topic', 'error'); return; }

    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const resultEl = document.getElementById('factory-result');
    resultEl.innerHTML = '<div class="empty-state">Generating... this may take 10-30 seconds.</div>';

    try {
        const data = await API.post('/api/ai/generate', {
            topic,
            platform: state.selectedPlatform,
            duration_target: parseInt(document.getElementById('factory-duration').value) || 30,
        });

        resultEl.innerHTML = `
            ${data.script ? `
            <div class="result-section">
                <h3>Script <button class="copy-btn" onclick="copyText(this, ${JSON.stringify(data.script).replace(/"/g, '&quot;')})">Copy</button></h3>
                <div class="pre-block">${esc(data.script)}</div>
            </div>` : ''}
            ${data.caption ? `
            <div class="result-section">
                <h3>Caption <button class="copy-btn" onclick="copyText(this, ${JSON.stringify(data.caption).replace(/"/g, '&quot;')})">Copy</button></h3>
                <div class="pre-block">${esc(data.caption)}</div>
            </div>` : ''}
            ${data.hashtags && data.hashtags.length ? `
            <div class="result-section">
                <h3>Hashtags <button class="copy-btn" onclick="copyText(this, ${JSON.stringify(data.hashtags.join(' ')).replace(/"/g, '&quot;')})">Copy</button></h3>
                <div class="hashtag-list">${data.hashtags.map(h => `<span class="hashtag-item">${esc(h)}</span>`).join('')}</div>
            </div>` : ''}
        `;

        toast('Generation complete!', 'success');
    } catch (e) {
        resultEl.innerHTML = `<div class="empty-state">Error: ${esc(e.message)}</div>`;
        toast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generate Script & Hashtags';
    }
}

function copyText(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 1500);
    }).catch(() => toast('Copy failed', 'error'));
}

// ── Utilities ──────────────────────────────────────────────
function esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
