import { showToast } from './common.js';

const VENUE_TYPES = [
    '', 'journal', 'conference', 'workshop', 'symposium', 'book', 'review',
    'news', 'study', 'meta_analysis', 'editorial', 'letters_and_comments',
    'case_report', 'clinical_trial', 'unknown', 'challenge', 'forum',
    'track', 'tutorials', 'seminar', 'preprint', 'dataset',
];

const INSTITUTION_CATEGORIES = ['', 'industry', 'academia', 'unknown'];

const PAGE_SIZE = 100;

// ── Venue state ───────────────────────────────────────────────────────────────

let _venueCurrentPage = 1;
let _venueCurrentQ = "";
let _venueDeletedOriginals = new Set();

export function initVenues() {
    loadVenueNorms();
    document.getElementById('addVenueNormBtn').addEventListener('click', addNewVenueRow);
    document.getElementById('saveVenueNormsBtn').addEventListener('click', saveVenueNorms);
    document.getElementById('venueSearch').addEventListener('input', debounce(() => {
        _venueCurrentQ = document.getElementById('venueSearch').value.trim();
        _venueCurrentPage = 1;
        loadVenueNorms();
    }, 150));
}

async function loadVenueNorms() {
    const tbody = document.getElementById('venueNormTbody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Loading…</td></tr>';
    try {
        const params = new URLSearchParams({ q: _venueCurrentQ, page: _venueCurrentPage, page_size: PAGE_SIZE });
        const response = await fetch(`/api/v1/norm/venues?${params}`);
        if (!response.ok) throw new Error('Failed to load venue normalizations');
        const data = await response.json();
        tbody.innerHTML = '';
        for (const entry of data.items) {
            tbody.appendChild(makeVenueRow(entry, false));
        }
        renderVenuePagination(data.total, data.pages);
    } catch (error) {
        tbody.innerHTML = '';
        showToast(`Error: ${error.message}`, 'error');
    }
}

function renderVenuePagination(total, totalPages) {
    const el = document.getElementById('venuePagination');
    const countHtml = `<span class="norm-count">${total} entr${total === 1 ? 'y' : 'ies'}</span>`;

    if (totalPages <= 1) {
        el.innerHTML = countHtml;
        return;
    }

    const page = _venueCurrentPage;
    const pages = buildPageList(page, totalPages);

    el.innerHTML = `
        ${countHtml}
        <div class="norm-page-controls">
            <button class="norm-page-btn" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>&#8249;</button>
            ${pages.map(p => p === null
                ? '<span class="norm-page-gap">…</span>'
                : `<button class="norm-page-btn${p === page ? ' active' : ''}" data-page="${p}">${p}</button>`
            ).join('')}
            <button class="norm-page-btn" data-page="${page + 1}" ${page === totalPages ? 'disabled' : ''}>&#8250;</button>
        </div>
    `;

    el.querySelectorAll('.norm-page-btn[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            _venueCurrentPage = parseInt(btn.dataset.page);
            loadVenueNorms();
        });
    });
}

function buildPageList(current, total) {
    const nums = new Set([1, total]);
    for (let p = current - 1; p <= current + 1; p++) {
        if (p >= 1 && p <= total) nums.add(p);
    }
    const sorted = [...nums].sort((a, b) => a - b);
    const result = [];
    let prev = 0;
    for (const p of sorted) {
        if (p - prev > 1) result.push(null);
        result.push(p);
        prev = p;
    }
    return result;
}

function addNewVenueRow() {
    const row = makeVenueRow({}, true);
    const tbody = document.getElementById('venueNewTbody');
    tbody.appendChild(row);
    syncVenueNewHeader(tbody);
    row.querySelector('.norm-original').focus();
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function syncVenueNewHeader(tbody) {
    const hasRows = tbody.querySelector('tr.norm-new-row') !== null;
    let header = tbody.querySelector('tr.norm-section-header');
    if (hasRows && !header) {
        header = document.createElement('tr');
        header.className = 'norm-section-header';
        header.innerHTML = '<td colspan="6" class="norm-new-label">New (unsaved) entries</td>';
        tbody.prepend(header);
    } else if (!hasRows && header) {
        header.remove();
    }
}

function makeVenueRow(entry, isNew) {
    const row = document.createElement('tr');
    if (isNew) row.classList.add('norm-new-row');
    else row.dataset.original = entry.original;
    row.innerHTML = `
        <td><input type="text" class="norm-original edit-input" value="${esc(entry.original || '')}" placeholder="Original name"></td>
        <td><input type="text" class="norm-name edit-input" value="${esc(entry.name || '')}" placeholder="Actual name"></td>
        <td><select class="norm-type edit-input">${venueTypeOptions(entry.type || '')}</select></td>
        <td><input type="text" class="norm-short-name edit-input" value="${esc(entry.short_name || '')}" placeholder="Short"></td>
        <td><input type="text" class="norm-date edit-input" value="${esc(entry.date || '')}" placeholder="YYYY[-MM[-DD]]"></td>
        <td class="cell-center"><button class="btn-remove-x">&times;</button></td>
    `;
    row.querySelector('.btn-remove-x').addEventListener('click', () => {
        if (isNew) {
            const tbody = row.closest('tbody');
            row.remove();
            syncVenueNewHeader(tbody);
        } else {
            _venueDeletedOriginals.add(row.dataset.original);
            row.remove();
        }
    });
    return row;
}

function collectVenueRows() {
    const newRows = [...document.querySelectorAll('#venueNewTbody tr.norm-new-row')];
    const pageRows = [...document.querySelectorAll('#venueNormTbody tr')];
    return [...newRows, ...pageRows].map(row => ({
        original:   row.querySelector('.norm-original').value.trim(),
        name:       row.querySelector('.norm-name').value.trim(),
        type:       row.querySelector('.norm-type').value.trim(),
        short_name: row.querySelector('.norm-short-name').value.trim(),
        date:       row.querySelector('.norm-date').value.trim(),
    })).filter(e => e.original);
}

async function saveVenueNorms() {
    const btn = document.getElementById('saveVenueNormsBtn');
    btn.textContent = 'Saving…';
    btn.disabled = true;
    try {
        if (_venueDeletedOriginals.size > 0) {
            const delResp = await fetch('/api/v1/norm/venues', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify([..._venueDeletedOriginals]),
            });
            if (!delResp.ok) {
                const err = await delResp.json();
                throw new Error(err.detail || err.message || 'Failed to delete');
            }
            _venueDeletedOriginals.clear();
        }
        const upsertEntries = collectVenueRows();
        if (upsertEntries.length > 0) {
            const saveResp = await fetch('/api/v1/norm/venues', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(upsertEntries),
            });
            if (!saveResp.ok) {
                const err = await saveResp.json();
                throw new Error(err.detail || err.message || 'Failed to save');
            }
        }
        showToast('Venue normalizations saved!', 'success');
        document.getElementById('venueNewTbody').innerHTML = '';
        loadVenueNorms();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    } finally {
        btn.textContent = 'Save';
        btn.disabled = false;
    }
}

// ── Institution state ─────────────────────────────────────────────────────────

let _instCurrentPage = 1;
let _instCurrentQ = "";
let _instDeletedOriginals = new Set();

export function initInstitutions() {
    loadInstNorms();
    document.getElementById('addInstNormBtn').addEventListener('click', addNewInstRow);
    document.getElementById('saveInstNormsBtn').addEventListener('click', saveInstNorms);
    document.getElementById('instSearch').addEventListener('input', debounce(() => {
        _instCurrentQ = document.getElementById('instSearch').value.trim();
        _instCurrentPage = 1;
        loadInstNorms();
    }, 150));
}

async function loadInstNorms() {
    const tbody = document.getElementById('instNormTbody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Loading…</td></tr>';
    try {
        const params = new URLSearchParams({ q: _instCurrentQ, page: _instCurrentPage, page_size: PAGE_SIZE });
        const response = await fetch(`/api/v1/norm/institutions?${params}`);
        if (!response.ok) throw new Error('Failed to load institution normalizations');
        const data = await response.json();
        tbody.innerHTML = '';
        for (const entry of data.items) {
            tbody.appendChild(makeInstRow(entry, false));
        }
        renderInstPagination(data.total, data.pages);
    } catch (error) {
        tbody.innerHTML = '';
        showToast(`Error: ${error.message}`, 'error');
    }
}

function renderInstPagination(total, totalPages) {
    const el = document.getElementById('instPagination');
    const countHtml = `<span class="norm-count">${total} entr${total === 1 ? 'y' : 'ies'}</span>`;

    if (totalPages <= 1) {
        el.innerHTML = countHtml;
        return;
    }

    const page = _instCurrentPage;
    const pages = buildPageList(page, totalPages);

    el.innerHTML = `
        ${countHtml}
        <div class="norm-page-controls">
            <button class="norm-page-btn" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>&#8249;</button>
            ${pages.map(p => p === null
                ? '<span class="norm-page-gap">…</span>'
                : `<button class="norm-page-btn${p === page ? ' active' : ''}" data-page="${p}">${p}</button>`
            ).join('')}
            <button class="norm-page-btn" data-page="${page + 1}" ${page === totalPages ? 'disabled' : ''}>&#8250;</button>
        </div>
    `;

    el.querySelectorAll('.norm-page-btn[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            _instCurrentPage = parseInt(btn.dataset.page);
            loadInstNorms();
        });
    });
}

function addNewInstRow() {
    const row = makeInstRow({}, true);
    const tbody = document.getElementById('instNewTbody');
    tbody.appendChild(row);
    syncInstNewHeader(tbody);
    row.querySelector('.norm-original').focus();
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function syncInstNewHeader(tbody) {
    const hasRows = tbody.querySelector('tr.norm-new-row') !== null;
    let header = tbody.querySelector('tr.norm-section-header');
    if (hasRows && !header) {
        header = document.createElement('tr');
        header.className = 'norm-section-header';
        header.innerHTML = '<td colspan="5" class="norm-new-label">New (unsaved) entries</td>';
        tbody.prepend(header);
    } else if (!hasRows && header) {
        header.remove();
    }
}

function makeInstRow(entry, isNew) {
    const row = document.createElement('tr');
    if (isNew) row.classList.add('norm-new-row');
    else row.dataset.original = entry.original;
    row.innerHTML = `
        <td><input type="text" class="norm-original edit-input" value="${esc(entry.original || '')}" placeholder="Original name"></td>
        <td><input type="text" class="norm-name edit-input" value="${esc(entry.name || '')}" placeholder="Actual name"></td>
        <td><select class="norm-category edit-input">${categoryOptions(entry.category || '')}</select></td>
        <td><input type="text" class="norm-country edit-input" value="${esc(entry.country || '')}" placeholder="Country"></td>
        <td class="cell-center"><button class="btn-remove-x">&times;</button></td>
    `;
    row.querySelector('.btn-remove-x').addEventListener('click', () => {
        if (isNew) {
            const tbody = row.closest('tbody');
            row.remove();
            syncInstNewHeader(tbody);
        } else {
            _instDeletedOriginals.add(row.dataset.original);
            row.remove();
        }
    });
    return row;
}

function collectInstRows() {
    const newRows = [...document.querySelectorAll('#instNewTbody tr.norm-new-row')];
    const pageRows = [...document.querySelectorAll('#instNormTbody tr')];
    return [...newRows, ...pageRows].map(row => ({
        original: row.querySelector('.norm-original').value.trim(),
        name:     row.querySelector('.norm-name').value.trim(),
        category: row.querySelector('.norm-category').value.trim(),
        country:  row.querySelector('.norm-country').value.trim(),
    })).filter(e => e.original);
}

async function saveInstNorms() {
    const btn = document.getElementById('saveInstNormsBtn');
    btn.textContent = 'Saving…';
    btn.disabled = true;
    try {
        if (_instDeletedOriginals.size > 0) {
            const delResp = await fetch('/api/v1/norm/institutions', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify([..._instDeletedOriginals]),
            });
            if (!delResp.ok) {
                const err = await delResp.json();
                throw new Error(err.detail || err.message || 'Failed to delete');
            }
            _instDeletedOriginals.clear();
        }
        const upsertEntries = collectInstRows();
        if (upsertEntries.length > 0) {
            const saveResp = await fetch('/api/v1/norm/institutions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(upsertEntries),
            });
            if (!saveResp.ok) {
                const err = await saveResp.json();
                throw new Error(err.detail || err.message || 'Failed to save');
            }
        }
        showToast('Institution normalizations saved!', 'success');
        document.getElementById('instNewTbody').innerHTML = '';
        loadInstNorms();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    } finally {
        btn.textContent = 'Save';
        btn.disabled = false;
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function venueTypeOptions(selected) {
    return VENUE_TYPES.map(t =>
        `<option value="${t}" ${t === selected ? 'selected' : ''}>${t || '—'}</option>`
    ).join('');
}

function categoryOptions(selected) {
    return INSTITUTION_CATEGORIES.map(c =>
        `<option value="${c}" ${c === selected ? 'selected' : ''}>${c || '—'}</option>`
    ).join('');
}

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function esc(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
