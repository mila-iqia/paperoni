import { html } from './common.js';
import { getScoreClass } from './paper.js';
import { createWorksetPaperElement, createDiffViewWithTabs } from './workset.js';

const PAGE_SIZE = 50;

const FILTER_OPTIONS = [
    { value: null, label: 'All' },
    { value: 'user', label: 'user' },
    { value: 'scraped', label: 'scraped' },
];

let pendingFilter = null;

/** Prefix with suggest: when sending to API if not already present. */
function toApiFlag(filter) {
    if (!filter) return null;
    return filter.startsWith('suggest:') ? filter : `suggest:${filter}`;
}

/**
 * Create comments display from paper.info.comments. Merge messages from same user.
 * Each comment has { user, comment }. Display user even if all messages are empty.
 * If oldComments is provided, only show comments not present in old (diff view).
 */
function createCommentsDisplay(comments, oldComments) {
    if (!comments || !Array.isArray(comments) || comments.length === 0) {
        return null;
    }

    const oldSet = new Set();
    if (oldComments && Array.isArray(oldComments)) {
        for (const c of oldComments) {
            const user = c?.user ?? 'Unknown';
            const msg = (c?.comment ?? '').trim();
            oldSet.add(`${user}\0${msg}`);
        }
    }

    const filtered = oldSet.size > 0
        ? comments.filter((c) => {
            const user = c?.user ?? 'Unknown';
            const msg = (c?.comment ?? '').trim();
            return !oldSet.has(`${user}\0${msg}`);
        })
        : comments;

    if (filtered.length === 0) return null;

    const byUser = new Map();
    for (const c of filtered) {
        const user = c?.user ?? 'Unknown';
        const msg = (c?.comment ?? '').trim();
        if (!byUser.has(user)) {
            byUser.set(user, []);
        }
        byUser.get(user).push(msg);
    }

    const items = [];
    for (const [user, messages] of byUser) {
        const merged = messages.filter(Boolean).join(' // ');
        items.push(html`
            <div class="pending-comment-item">
                <span class="pending-comment-user">From ${user}${merged ? ': ' : ''}</span>
                ${merged ? html`<span class="pending-comment-text">${merged}</span>` : null}
            </div>
        `);
    }

    return html`
        <div class="pending-comments">
            ${items}
        </div>
    `;
}

const approvedIds = new Set();
const rejectedIds = new Set();

let selectedPendingIndex = 0;
let pendingKeydownHandler = null;

function getPendingItems() {
    const list = document.querySelector('#pendingContainer .workset-list');
    return list ? list.querySelectorAll('.workset-item') : [];
}

function updatePendingSelection() {
    const items = getPendingItems();
    items.forEach((el, i) => el.classList.toggle('pending-selected', i === selectedPendingIndex));
    const selected = items[selectedPendingIndex];
    if (selected) {
        selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
}

function attachPendingKeyboard() {
    if (pendingKeydownHandler) {
        document.removeEventListener('keydown', pendingKeydownHandler);
    }
    pendingKeydownHandler = (e) => {
        const container = document.getElementById('pendingContainer');
        const list = container?.querySelector('.workset-list');
        if (!list) return;
        const items = getPendingItems();
        if (items.length === 0) return;
        const tag = (e.target?.tagName || '').toUpperCase();
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                selectedPendingIndex = Math.min(selectedPendingIndex + 1, items.length - 1);
                updatePendingSelection();
                break;
            case 'ArrowUp':
                e.preventDefault();
                selectedPendingIndex = Math.max(0, selectedPendingIndex - 1);
                updatePendingSelection();
                break;
            case 'a':
            case 'y':
                e.preventDefault();
                approveSelectedAndNext(items);
                break;
            case 'r':
            case 'n':
                e.preventDefault();
                rejectSelectedAndNext(items);
                break;
            default:
                break;
        }
    };
    document.addEventListener('keydown', pendingKeydownHandler);
}

function getPaperIdFromItem(item) {
    if (!item) return null;
    return item.dataset?.paperId || item.querySelector('[data-paper-id]')?.dataset?.paperId || null;
}

function approveSelectedAndNext(items) {
    const paperId = getPaperIdFromItem(items[selectedPendingIndex]);
    if (!paperId) return;
    rejectedIds.delete(paperId);
    approvedIds.add(paperId);
    updateConfirmToast();
    selectedPendingIndex = Math.min(selectedPendingIndex + 1, items.length - 1);
    updatePendingSelection();
}

function rejectSelectedAndNext(items) {
    const paperId = getPaperIdFromItem(items[selectedPendingIndex]);
    if (!paperId) return;
    approvedIds.delete(paperId);
    rejectedIds.add(paperId);
    updateConfirmToast();
    selectedPendingIndex = Math.min(selectedPendingIndex + 1, items.length - 1);
    updatePendingSelection();
}

function updateButtonStates() {
    document.querySelectorAll('.btn-approve-pending[data-paper-id]').forEach(btn => {
        const id = btn.dataset.paperId;
        const isApproved = approvedIds.has(id);
        const isRejected = rejectedIds.has(id);
        btn.classList.toggle('selected', isApproved);
        btn.classList.toggle('faded', isRejected);
        btn.textContent = isApproved ? '✓ Approve' : 'Approve';
    });
    document.querySelectorAll('.btn-reject-pending[data-paper-id]').forEach(btn => {
        const id = btn.dataset.paperId;
        const isApproved = approvedIds.has(id);
        const isRejected = rejectedIds.has(id);
        btn.classList.toggle('selected', isRejected);
        btn.classList.toggle('faded', isApproved);
        btn.textContent = isRejected ? '✓ Reject' : 'Reject';
    });
}

function updateConfirmToast() {
    const approveCount = approvedIds.size;
    const rejectCount = rejectedIds.size;
    if (approveCount === 0 && rejectCount === 0) {
        const existing = document.getElementById('pending-confirm-toast');
        if (existing) existing.remove();
        updateButtonStates();
        return;
    }

    let toast = document.getElementById('pending-confirm-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'pending-confirm-toast';
        toast.className = 'toast pending-confirm-toast';
        document.body.appendChild(toast);
    }

    const parts = [];
    if (approveCount > 0) {
        parts.push(`Approve ${approveCount} change${approveCount !== 1 ? 's' : ''}`);
    }
    if (rejectCount > 0) {
        parts.push(`Reject ${rejectCount} change${rejectCount !== 1 ? 's' : ''}`);
    }

    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'btn-confirm-pending';
    confirmBtn.textContent = 'Confirm changes';

    toast.innerHTML = '';
    toast.appendChild(document.createTextNode(parts.join(', ') + '. '));
    toast.appendChild(confirmBtn);

    updateButtonStates();

    confirmBtn.onclick = async () => {
        const approve = [...approvedIds];
        const reject = [...rejectedIds];
        toast.remove();
        approvedIds.clear();
        rejectedIds.clear();

        try {
            const response = await fetch('/api/v1/pending/decide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approve, reject }),
            });
            const result = await response.json();
            if (result.success) {
                displayPending();
            }
        } catch (err) {
            console.error('Failed to decide:', err);
        }
    };
}

function setResults(...elements) {
    const container = document.getElementById('pendingContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

function createFilterBar() {
    const bar = html`
        <div class="pending-filter-bar">
            ${FILTER_OPTIONS.map(({ value, label }) => {
                const btn = html`<button type="button" class="pending-filter-btn" data-filter="${value ?? ''}">${label}</button>`;
                btn.classList.toggle('active', pendingFilter === value);
                btn.addEventListener('click', () => {
                    pendingFilter = value;
                    updatePendingUrl(0);
                    loadPending(0);
                });
                return btn;
            })}
        </div>
    `;
    return bar;
}

function createPagination(offset, count, total, nextOffset) {
    const start = offset + 1;
    const end = offset + count;
    const paperWord = total !== 1 ? 'papers' : 'paper';

    const prevButton = html`<button disabled="${offset === 0}">Previous</button>`;
    prevButton.onclick = () => {
        const newOffset = Math.max(0, offset - PAGE_SIZE);
        loadPending(newOffset);
    };

    const nextButton = html`<button disabled="${nextOffset === null}">Next</button>`;
    nextButton.onclick = () => {
        if (nextOffset !== null) {
            loadPending(nextOffset);
        }
    };

    return html`
        <div class="pagination">
            <div class="results-info"><span class="count">${total}</span> ${paperWord} found</div>
            ${prevButton}
            <div class="page-info">Showing ${start}-${end} of ${total}</div>
            ${nextButton}
        </div>
    `;
}

async function fetchPending(offset = 0, limit = PAGE_SIZE, filter = null) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
        expand_links: 'true',
    });
    const apiFlag = toApiFlag(filter);
    if (apiFlag) {
        queryParams.append('flags', apiFlag);
    }

    const url = `/api/v1/pending/list?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function createPendingItem(paperDiff) {
    const current = paperDiff.current;
    const paperNew = paperDiff.new;
    const score = paperDiff.score;
    const isDelete = current && (paperNew?.flags || []).includes('mark:delete');
    const paperId = paperNew?.id ?? current?.id;

    const scoreBand = (score != null)
        ? html`
            <div class="score-band ${getScoreClass(score)}">
                <div class="score-value">${Math.round(score)}</div>
            </div>
        `
        : null;

    let contentEl;
    if (isDelete) {
        // Delete suggestion: comments and label outside, paper with light red background only
        const paperContent = createWorksetPaperElement(current, { excludeFromInfo: ['comments'] });
        const oldComments = current?.info?.comments;
        const commentsEl = createCommentsDisplay(paperNew?.info?.comments, oldComments);
        contentEl = html`
            <div class="pending-delete-wrapper">
                ${commentsEl}
                <div class="pending-delete-label">Delete paper</div>
                <div class="pending-delete-paper">${paperContent}</div>
            </div>
        `;
    } else if (!current) {
        // New paper suggestion - display like search (using workset paper format)
        contentEl = createWorksetPaperElement(paperNew, { excludeFromInfo: ['comments'], editSuggest: true });
    } else {
        // Diff between current (old) and new (suggestion)
        contentEl = createDiffViewWithTabs(current, paperNew);
    }

    if (!isDelete) {
        const oldComments = current?.info?.comments;
        const commentsEl = createCommentsDisplay(paperNew?.info?.comments, oldComments);
        if (commentsEl) {
            const wrapper = document.createElement('div');
            wrapper.className = 'pending-with-comments';
            const tabsEl = contentEl.querySelector('.workset-tabs');
            if (tabsEl) {
                tabsEl.insertBefore(commentsEl, tabsEl.firstChild);
            } else {
                wrapper.appendChild(commentsEl);
                wrapper.appendChild(contentEl);
                contentEl = wrapper;
            }
        }
    }

    const approveBtn = html`<button class="btn-approve-pending">Approve</button>`;
    const rejectBtn = html`<button class="btn-reject-pending">Reject</button>`;

    if (paperId) {
        approveBtn.dataset.paperId = paperId;
        rejectBtn.dataset.paperId = paperId;
        approveBtn.addEventListener('click', () => {
            rejectedIds.delete(paperId);
            if (approvedIds.has(paperId)) {
                approvedIds.delete(paperId);
            } else {
                approvedIds.add(paperId);
            }
            updateConfirmToast();
        });
        rejectBtn.addEventListener('click', () => {
            approvedIds.delete(paperId);
            if (rejectedIds.has(paperId)) {
                rejectedIds.delete(paperId);
            } else {
                rejectedIds.add(paperId);
            }
            updateConfirmToast();
        });
    }

    const actionBar = html`
        <div class="pending-actions">
            ${approveBtn}
            ${rejectBtn}
        </div>
    `;

    const itemEl = html`
        <div class="workset-item" data-paper-id="${paperId ?? ''}">
            <div class="workset-content">
                ${scoreBand}
                <div class="workset-tabs">
                    <div class="tab-contents" style="border: none; padding: 0;">
                        <div class="tab-content active" style="display: block;">
                            ${contentEl}
                            ${actionBar}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    return itemEl;
}

function renderPending(data, offset = 0) {
    approvedIds.clear();
    rejectedIds.clear();
    const existingToast = document.getElementById('pending-confirm-toast');
    if (existingToast) existingToast.remove();

    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                No pending papers.
            </div>
        `;
        setResults(createFilterBar(), noResults);
        return;
    }

    const paginationTop = createPagination(
        offset,
        data.count,
        data.total,
        data.next_offset,
    );
    const items = data.results.map(paperDiff => createPendingItem(paperDiff));
    const list = html`<div class="workset-list">${items}</div>`;
    const paginationBottom = data.total > PAGE_SIZE
        ? createPagination(offset, data.count, data.total, data.next_offset)
        : null;
    setResults(createFilterBar(), paginationTop, list, paginationBottom);
    selectedPendingIndex = 0;
    updatePendingSelection();
    updateButtonStates();
    attachPendingKeyboard();
}

function displayLoading() {
    setResults(createFilterBar(), html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(createFilterBar(), html`<div class="error-message">Error loading pending: ${error.message}</div>`);
}

function updatePendingUrl(offset) {
    const urlParams = new URLSearchParams();
    if (offset > 0) {
        urlParams.set('offset', offset.toString());
    }
    if (pendingFilter) {
        urlParams.set('filter', pendingFilter);
    }
    const newUrl = urlParams.toString()
        ? `${window.location.pathname}?${urlParams.toString()}`
        : window.location.pathname;
    window.history.replaceState({}, '', newUrl);
}

export async function loadPending(offset = 0) {
    displayLoading();
    updatePendingUrl(offset);

    try {
        const data = await fetchPending(offset, PAGE_SIZE, pendingFilter);
        renderPending(data, offset);
    } catch (error) {
        console.error('Failed to load pending:', error);
        displayError(error);
    }
}

export async function displayPending() {
    const urlParams = new URLSearchParams(window.location.search);
    const offset = parseInt(urlParams.get('offset') || '0', 10);
    const filterParam = urlParams.get('filter');
    if (filterParam) {
        pendingFilter = filterParam;
    }
    await loadPending(offset);
}
