import { html } from './common.js';
import { getScoreClass } from './paper.js';
import { createWorksetPaperElement, createDiffViewWithTabs } from './workset.js';

const PAGE_SIZE = 100;

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
        parts.push(`Approve ${approveCount} paper${approveCount !== 1 ? 's' : ''}`);
    }
    if (rejectCount > 0) {
        parts.push(`Reject ${rejectCount} paper${rejectCount !== 1 ? 's' : ''}`);
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

async function fetchPending(offset = 0, limit = PAGE_SIZE) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
        expand_links: 'true',
    });

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
    const paperId = paperNew?.id;

    const scoreBand = (score != null)
        ? html`
            <div class="score-band ${getScoreClass(score)}">
                <div class="score-value">${Math.round(score)}</div>
            </div>
        `
        : null;

    let contentEl;
    if (!current) {
        // New paper suggestion - display like search (using workset paper format)
        contentEl = createWorksetPaperElement(paperNew, { excludeFromInfo: ['comments'], editSuggest: true });
    } else {
        // Diff between current (old) and new (suggestion)
        contentEl = createDiffViewWithTabs(current, paperNew);
    }

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

    return html`
        <div class="workset-item">
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
}

function renderPending(data) {
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
        setResults(noResults);
        return;
    }

    const items = data.results.map(paperDiff => createPendingItem(paperDiff));
    const list = html`<div class="workset-list">${items}</div>`;
    setResults(list);
    updateButtonStates();
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading pending: ${error.message}</div>`);
}

export async function displayPending() {
    displayLoading();

    try {
        const data = await fetchPending();
        renderPending(data);
    } catch (error) {
        console.error('Failed to load pending:', error);
        displayError(error);
    }
}
