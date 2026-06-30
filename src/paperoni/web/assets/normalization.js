import { showToast } from './common.js';

// ── Remap modal ───────────────────────────────────────────────────────────────

let _remapCallback = null;

function _initRemapModal() {
    const el = document.createElement('div');
    el.id = 'norm-remap-modal';
    el.hidden = true;
    el.innerHTML = `
        <div class="norm-modal-overlay">
            <div class="norm-modal-dialog">
                <h3 class="norm-modal-title">Rename actual name</h3>
                <p class="norm-modal-desc">The old name will also be added as an original (<code id="norm-modal-normalized"></code>) that maps to the new name.</p>
                <input type="text" id="norm-modal-input" class="edit-input norm-modal-input" autocomplete="off">
                <div class="norm-modal-actions">
                    <button id="norm-modal-cancel" class="norm-modal-btn">Cancel</button>
                    <button id="norm-modal-confirm" class="norm-modal-btn norm-modal-confirm">Confirm</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(el);
    el.querySelector('.norm-modal-overlay').addEventListener('click', e => {
        if (e.target === e.currentTarget) _closeRemapModal(false);
    });
    document.getElementById('norm-modal-cancel').addEventListener('click', () => _closeRemapModal(false));
    document.getElementById('norm-modal-confirm').addEventListener('click', () => _closeRemapModal(true));
    document.getElementById('norm-modal-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') _closeRemapModal(true);
        if (e.key === 'Escape') _closeRemapModal(false);
    });
}

function _closeRemapModal(confirmed) {
    const el = document.getElementById('norm-remap-modal');
    if (!el) return;
    el.hidden = true;
    if (confirmed && _remapCallback) {
        const newName = document.getElementById('norm-modal-input').value.trim();
        if (newName) _remapCallback(newName);
    }
    _remapCallback = null;
}

async function openRemapModal(oldName, normType, callback) {
    if (!document.getElementById('norm-remap-modal')) _initRemapModal();
    let normalized;
    try {
        const resp = await fetch(`/api/v1/norm/normalize?${new URLSearchParams({name: oldName, type: normType})}`);
        if (resp.ok) ({ normalized } = await resp.json());
    } catch (e) { /* ignore — fallback below */ }
    if (!normalized) {
        showToast('Could not reach normalize endpoint', 'error');
        return;
    }
    document.getElementById('norm-modal-normalized').textContent = normalized;
    const input = document.getElementById('norm-modal-input');
    input.value = oldName;
    document.getElementById('norm-remap-modal').hidden = false;
    input.select();
    input.focus();
    _remapCallback = (newName) => callback(newName, normalized);
}

// ── Constants ─────────────────────────────────────────────────────────────────

const VENUE_TYPES = [
    '', 'journal', 'conference', 'workshop', 'symposium', 'book', 'review',
    'news', 'study', 'meta_analysis', 'editorial', 'letters_and_comments',
    'case_report', 'clinical_trial', 'unknown', 'challenge', 'forum',
    'track', 'tutorials', 'seminar', 'preprint', 'dataset',
];

const INSTITUTION_CATEGORIES = ['', 'industry', 'academia', 'unknown'];

const PAGE_SIZE = 100;

const hasDirty = id => !!document.querySelector(`#${id} .norm-dirty-row`);

// ── Venue state ───────────────────────────────────────────────────────────────

let _venueCurrentPage = 1;
let _venueCurrentQ = "";
let _venueDeletedOriginals = new Set();

export function initVenues() {
    loadVenueNorms();
    document.getElementById('addVenueNormBtn').addEventListener('click', addNewVenueRow);
    document.getElementById('saveVenueNormsBtn').addEventListener('click', saveVenueNorms);
    document.getElementById('venueSearch').addEventListener('input', debounce(() => {
        if (hasDirty('venueNormTbody')) {
            showToast('Save or revert changes before searching', 'error');
            document.getElementById('venueSearch').value = _venueCurrentQ;
            return;
        }
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
            if (hasDirty('venueNormTbody')) {
                showToast('Save or revert changes before changing pages', 'error');
                return;
            }
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

function makeVenueRow(entry, isNew, savedEntry = null) {
    const row = document.createElement('tr');
    if (isNew) {
        row.classList.add('norm-new-row');
        if (savedEntry) {
            row.classList.add('norm-edit-row');
            row.dataset.savedVals = JSON.stringify([
                savedEntry.original || '', savedEntry.name || '',
                savedEntry.type || '', savedEntry.short_name || '', savedEntry.date || '',
            ]);
        }
    } else {
        row.dataset.original = entry.original;
        row.dataset.savedVals = JSON.stringify([
            entry.original || '', entry.name || '',
            entry.type || '', entry.short_name || '', entry.date || '',
        ]);
    }
    row.innerHTML = `
        <td><input type="text" class="norm-original edit-input" value="${esc(entry.original || '')}" placeholder="Original name"></td>
        <td class="norm-name-cell"><div class="norm-name-inner"><input type="text" class="norm-name edit-input" value="${esc(entry.name || '')}" placeholder="Actual name"><button class="norm-remap-btn" title="Remap this name">&#9654;</button></div></td>
        <td><select class="norm-type edit-input">${venueTypeOptions(entry.type || '')}</select></td>
        <td><input type="text" class="norm-short-name edit-input" value="${esc(entry.short_name || '')}" placeholder="Short"></td>
        <td><input type="text" class="norm-date edit-input" value="${esc(entry.date || '')}" placeholder="YYYY[-MM[-DD]]"></td>
        <td class="cell-center"><button class="btn-remove-x">&times;</button></td>
    `;
    if (!isNew || savedEntry) {
        const inputs = [
            row.querySelector('.norm-original'), row.querySelector('.norm-name'),
            row.querySelector('.norm-type'),     row.querySelector('.norm-short-name'),
            row.querySelector('.norm-date'),
        ];
        const actionBtn = row.querySelector('.btn-remove-x');
        const onDelete = isNew
            ? () => { const tbody = row.closest('tbody'); row.remove(); syncVenueNewHeader(tbody); }
            : () => { _venueDeletedOriginals.add(row.dataset.original); row.remove(); };
        const checkDirty = () => {
            const saved = JSON.parse(row.dataset.savedVals);
            const dirty = inputs.some((el, i) => el.value !== saved[i]);
            row.classList.toggle('norm-dirty-row', dirty);
            actionBtn.innerHTML = dirty ? '&#x21BA;' : '&times;';
            actionBtn.className = dirty ? 'btn-revert' : 'btn-remove-x';
            actionBtn.title = dirty ? 'Revert changes' : '';
        };
        inputs.forEach(el => { el.addEventListener('input', checkDirty); el.addEventListener('change', checkDirty); });
        actionBtn.addEventListener('click', () => {
            if (row.classList.contains('norm-dirty-row')) {
                const saved = JSON.parse(row.dataset.savedVals);
                inputs.forEach((el, i) => { el.value = saved[i]; });
                checkDirty();
            } else {
                onDelete();
            }
        });
        if (savedEntry) checkDirty(); // initialize dirty state immediately
    } else {
        row.querySelector('.btn-remove-x').addEventListener('click', () => {
            const tbody = row.closest('tbody');
            row.remove();
            syncVenueNewHeader(tbody);
        });
    }
    row.querySelector('.norm-remap-btn').addEventListener('click', () => {
        const oldName = row.querySelector('.norm-name').value.trim();
        if (!oldName) return;
        openRemapModal(oldName, 'venue', async (newName, normalized) => {
            if (newName === oldName) return;
            // Update current row in place
            row.querySelector('.norm-name').value = newName;
            if (!isNew) row.querySelector('.norm-name').dispatchEvent(new Event('input'));
            // Fetch all other entries with old name, show them with new name
            const tbody = document.getElementById('venueNewTbody');
            try {
                const resp = await fetch(`/api/v1/norm/venues/by-name?${new URLSearchParams({name: oldName})}`);
                if (resp.ok) {
                    for (const entry of await resp.json()) {
                        if (entry.original === row.dataset.original) continue;
                        // Hide the page row for this entry so it isn't double-sent on save
                        for (const pr of document.querySelectorAll('#venueNormTbody tr')) {
                            if (pr.querySelector('.norm-original')?.value === entry.original) {
                                pr.dataset.superseded = '1';
                                pr.style.display = 'none';
                            }
                        }
                        tbody.appendChild(makeVenueRow({...entry, name: newName}, true, entry));
                    }
                }
            } catch (e) { /* ignore */ }
            // Remap row: maps normalize(oldName) → newName (truly new, no savedEntry)
            tbody.appendChild(makeVenueRow({
                original: normalized,
                name: newName,
                type: row.querySelector('.norm-type').value,
                short_name: row.querySelector('.norm-short-name').value,
                date: row.querySelector('.norm-date').value,
            }, true));
            syncVenueNewHeader(tbody);
        });
    });
    return row;
}

function collectVenueRows() {
    const newRows = [...document.querySelectorAll('#venueNewTbody tr.norm-new-row')];
    const pageRows = [...document.querySelectorAll('#venueNormTbody tr')]
        .filter(r => !r.dataset.superseded);
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
        if (hasDirty('instNormTbody')) {
            showToast('Save or revert changes before searching', 'error');
            document.getElementById('instSearch').value = _instCurrentQ;
            return;
        }
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
            if (hasDirty('instNormTbody')) {
                showToast('Save or revert changes before changing pages', 'error');
                return;
            }
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

function makeInstRow(entry, isNew, savedEntry = null) {
    const row = document.createElement('tr');
    if (isNew) {
        row.classList.add('norm-new-row');
        if (savedEntry) {
            row.classList.add('norm-edit-row');
            row.dataset.savedVals = JSON.stringify([
                savedEntry.original || '', savedEntry.name || '',
                savedEntry.category || '', savedEntry.country || '',
            ]);
        }
    } else {
        row.dataset.original = entry.original;
        row.dataset.savedVals = JSON.stringify([
            entry.original || '', entry.name || '',
            entry.category || '', entry.country || '',
        ]);
    }
    row.innerHTML = `
        <td><input type="text" class="norm-original edit-input" value="${esc(entry.original || '')}" placeholder="Original name"></td>
        <td class="norm-name-cell"><div class="norm-name-inner"><input type="text" class="norm-name edit-input" value="${esc(entry.name || '')}" placeholder="Actual name"><button class="norm-remap-btn" title="Remap this name">&#9654;</button></div></td>
        <td><select class="norm-category edit-input">${categoryOptions(entry.category || '')}</select></td>
        <td><input type="text" class="norm-country edit-input" value="${esc(entry.country || '')}" placeholder="Country"></td>
        <td class="cell-center"><button class="btn-remove-x">&times;</button></td>
    `;
    if (!isNew || savedEntry) {
        const inputs = [
            row.querySelector('.norm-original'), row.querySelector('.norm-name'),
            row.querySelector('.norm-category'), row.querySelector('.norm-country'),
        ];
        const actionBtn = row.querySelector('.btn-remove-x');
        const onDelete = isNew
            ? () => { const tbody = row.closest('tbody'); row.remove(); syncInstNewHeader(tbody); }
            : () => { _instDeletedOriginals.add(row.dataset.original); row.remove(); };
        const checkDirty = () => {
            const saved = JSON.parse(row.dataset.savedVals);
            const dirty = inputs.some((el, i) => el.value !== saved[i]);
            row.classList.toggle('norm-dirty-row', dirty);
            actionBtn.innerHTML = dirty ? '&#x21BA;' : '&times;';
            actionBtn.className = dirty ? 'btn-revert' : 'btn-remove-x';
            actionBtn.title = dirty ? 'Revert changes' : '';
        };
        inputs.forEach(el => { el.addEventListener('input', checkDirty); el.addEventListener('change', checkDirty); });
        actionBtn.addEventListener('click', () => {
            if (row.classList.contains('norm-dirty-row')) {
                const saved = JSON.parse(row.dataset.savedVals);
                inputs.forEach((el, i) => { el.value = saved[i]; });
                checkDirty();
            } else {
                onDelete();
            }
        });
        if (savedEntry) checkDirty(); // initialize dirty state immediately
    } else {
        row.querySelector('.btn-remove-x').addEventListener('click', () => {
            const tbody = row.closest('tbody');
            row.remove();
            syncInstNewHeader(tbody);
        });
    }
    row.querySelector('.norm-remap-btn').addEventListener('click', () => {
        const oldName = row.querySelector('.norm-name').value.trim();
        if (!oldName) return;
        openRemapModal(oldName, 'institution', async (newName, normalized) => {
            if (newName === oldName) return;
            // Update current row in place
            row.querySelector('.norm-name').value = newName;
            if (!isNew) row.querySelector('.norm-name').dispatchEvent(new Event('input'));
            // Fetch all other entries with old name, show them with new name
            const tbody = document.getElementById('instNewTbody');
            try {
                const resp = await fetch(`/api/v1/norm/institutions/by-name?${new URLSearchParams({name: oldName})}`);
                if (resp.ok) {
                    for (const entry of await resp.json()) {
                        if (entry.original === row.dataset.original && entry.name === oldName) continue;
                        // Hide the matching page row so it isn't double-sent on save
                        for (const pr of document.querySelectorAll('#instNormTbody tr')) {
                            if (pr.querySelector('.norm-original')?.value === entry.original &&
                                pr.querySelector('.norm-name')?.value === oldName) {
                                pr.dataset.superseded = '1';
                                pr.style.display = 'none';
                            }
                        }
                        tbody.appendChild(makeInstRow({...entry, name: newName}, true, entry));
                    }
                }
            } catch (e) { /* ignore */ }
            // Remap row: maps normalize(oldName) → newName (truly new, no savedEntry)
            tbody.appendChild(makeInstRow({
                original: normalized,
                name: newName,
                category: row.querySelector('.norm-category').value,
                country: row.querySelector('.norm-country').value,
            }, true));
            syncInstNewHeader(tbody);
        });
    });
    return row;
}

function collectInstRows() {
    const newRows = [...document.querySelectorAll('#instNewTbody tr.norm-new-row')];
    const pageRows = [...document.querySelectorAll('#instNormTbody tr')]
        .filter(r => !r.dataset.superseded);
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
