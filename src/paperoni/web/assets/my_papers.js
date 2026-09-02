import { debounce, html, showToast } from './common.js';
import { getTranslation, setLanguageNode } from './translate.js';
import { createPaperResultElement } from './search.js';
import { createPendingItem } from './pending.js';
import { matchesSearch } from './paper.js';

const PAGE_SIZE = 50;

// The email papers are searched/claimed against. Defaults to the logged-in
// user's email but can be overridden (via the "claim-for" URL parameter, or
// by editing the "Claiming for" field) to search/claim on someone else's
// behalf.
let userEmail = '';
// The logged-in user's own email, used as the fallback default.
let loginEmail = '';
let suggestMode = false;
let currentTitle = '';
// The API's `author` query param only accepts one value and only means
// "match by email" OR "match by name", never both -- and the claimed
// section already spends that slot on `userEmail`. So the author-name
// filter is applied server-side for the unclaimed section (which is free to
// use it normally), and client-side for the claimed section (see
// `paperMatchesAuthor`/`pendingMatchesAuthor`).
let currentAuthor = '';

// The claimed section's currently displayed page. Kept around so the
// "Unclaimed papers" section can exclude whatever is currently on screen
// there without an extra round trip.
let claimedPage = null;
// The unclaimed section's last-fetched (unfiltered) page. Kept around so that
// when the claimed page changes we can re-apply the exclusion set locally
// instead of re-querying the server.
let unclaimedRawPage = null;

// When unclaiming goes through /api/v1/suggest (non-validators), the main
// collection still has the original email -- only the pending suggestion
// reflects the unclaim -- so a plain re-fetch of the claimed section would
// show the paper as claimed again. As a relatively simple workaround (this
// is a display quirk, not a data-integrity issue), we remember locally which
// paper ids were unclaimed this way, and for those specifically, double-check
// the suggestions db (via ?latest_edit=true) before trusting the main
// collection's claimed status.
const LOCALLY_UNCLAIMED_STORAGE_KEY = 'paperoni-my-papers-locally-unclaimed';

function readLocallyUnclaimedStore() {
    try {
        const raw = JSON.parse(localStorage.getItem(LOCALLY_UNCLAIMED_STORAGE_KEY));
        return raw && typeof raw === 'object' ? raw : {};
    } catch {
        return {};
    }
}

function getLocallyUnclaimedIds(email) {
    return new Set(readLocallyUnclaimedStore()[email] ?? []);
}

function setLocallyUnclaimed(email, paperId, unclaimed) {
    if (paperId == null) return;
    try {
        const store = readLocallyUnclaimedStore();
        const ids = new Set(store[email] ?? []);
        if (unclaimed) {
            ids.add(paperId);
        } else {
            ids.delete(paperId);
        }
        if (ids.size > 0) {
            store[email] = [...ids];
        } else {
            delete store[email];
        }
        localStorage.setItem(LOCALLY_UNCLAIMED_STORAGE_KEY, JSON.stringify(store));
    } catch {
        // Storage unavailable (private mode, etc.): the workaround just won't persist.
    }
}

/**
 * For validated results whose id was locally marked as unclaimed-via-suggestion,
 * confirm against the suggestions db (which may since have been approved,
 * rejected, or superseded) rather than trusting the main collection: drop the
 * paper if the latest (possibly-pending) state really doesn't credit us
 * anymore, and forget the local mark if it turns out to be stale.
 */
async function reconcileLocallyUnclaimed(validatedResults) {
    const locallyUnclaimed = getLocallyUnclaimedIds(userEmail);
    if (locallyUnclaimed.size === 0) return validatedResults;

    const checked = await Promise.all(validatedResults.map(async (paper) => {
        if (paper.id == null || !locallyUnclaimed.has(paper.id)) {
            return paper;
        }
        try {
            const response = await fetch(`/api/v1/paper/${paper.id}?latest_edit=true`);
            if (!response.ok) return paper;
            const latest = await response.json();
            if ((latest.authors ?? []).some(isMe)) {
                // Rejected, approved-and-reverted, or otherwise stale: forget it.
                setLocallyUnclaimed(userEmail, paper.id, false);
                return paper;
            }
            return null;
        } catch {
            return paper;
        }
    }));

    return checked.filter(Boolean);
}

async function fetchSearchResults(params, offset, limit) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
        expand_links: 'true',
    });
    if (params.title) queryParams.append('title', params.title);
    if (params.author) queryParams.append('author', params.author);

    const response = await fetch(`/api/v1/search?${queryParams.toString()}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
}

async function fetchPendingResults(params, offset, limit) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
        expand_links: 'true',
    });
    if (params.title) queryParams.append('title', params.title);
    if (params.author) queryParams.append('author', params.author);

    const response = await fetch(`/api/v1/pending/list?${queryParams.toString()}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
}

/**
 * Fetch one page of combined validated+pending results: validated papers fill
 * the page first, and pending papers are only queried once validated is
 * exhausted (mirrors the search page's behaviour with both filters checked).
 */
async function fetchPage(params, offset) {
    const validated = await fetchSearchResults(params, offset, PAGE_SIZE);
    const validatedTotal = validated.total ?? 0;
    const validatedResults = validated.results ?? [];
    const remainder = PAGE_SIZE - validatedResults.length;
    const validatedNext = validated.next_offset ?? null;

    let pendingResults = [];
    let pendingTotal = null;
    let nextOffset = validatedNext;

    if (validatedNext === null) {
        const pendingOffset = Math.max(0, offset - validatedTotal);
        const pending = await fetchPendingResults(params, pendingOffset, Math.max(1, remainder));
        pendingTotal = pending.total ?? 0;
        pendingResults = (pending.results ?? []).slice(0, remainder);
        if (pendingOffset + pendingResults.length < pendingTotal) {
            nextOffset = offset + validatedResults.length + pendingResults.length;
        }
    }

    return {
        offset,
        validatedResults,
        pendingResults,
        count: validatedResults.length + pendingResults.length,
        total: validatedTotal + (pendingTotal ?? 0),
        validatedTotal,
        pendingTotal,
        next_offset: nextOffset,
    };
}

async function submitPaper(paper, comment, suggest) {
    const endpoint = suggest ? '/api/v1/suggest' : '/api/v1/include';
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ papers: [paper], comment: comment || '' }),
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }
    return await response.json();
}

function isMe(author) {
    const email = author?.author?.email;
    return !!email && email.trim().toLowerCase() === userEmail.trim().toLowerCase();
}

function pendingId(diff) {
    return diff.new?.id ?? diff.current?.id ?? null;
}

// Client-side author-name filter for the claimed section (the API's `author`
// param is already spent on the email match there -- see `currentAuthor`
// above).
function paperMatchesAuthor(paper, authorFilter) {
    if (!authorFilter) return true;
    return (paper.authors ?? []).some(a => matchesSearch(a.display_name, authorFilter));
}

function pendingMatchesAuthor(diff, authorFilter) {
    if (!authorFilter) return true;
    return paperMatchesAuthor(diff.new ?? diff.current ?? {}, authorFilter);
}

/** Levenshtein (edit) distance between two strings. */
function editDistance(a, b) {
    a = a || '';
    b = b || '';
    const m = a.length;
    const n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;

    const row = new Array(n + 1);
    for (let j = 0; j <= n; j++) row[j] = j;

    for (let i = 1; i <= m; i++) {
        let prevDiag = row[0];
        row[0] = i;
        for (let j = 1; j <= n; j++) {
            const temp = row[j];
            row[j] = a[i - 1] === b[j - 1]
                ? prevDiag
                : 1 + Math.min(prevDiag, row[j], row[j - 1]);
            prevDiag = temp;
        }
    }
    return row[n];
}

/**
 * Name hints for "which author are you?": the local part of the email
 * ("claiming for" address, before the "@") plus every display name this
 * email is already credited under on the claimed section's current page.
 * Computed from `claimedPage`, which is only populated once the claimed
 * list has been fetched -- no extra query needed.
 */
function myNameHints() {
    const hints = new Set();

    const localPart = userEmail.split('@')[0]?.trim();
    if (localPart) hints.add(localPart);

    if (claimedPage) {
        const authorsOnClaimedPapers = [
            ...claimedPage.validatedResults.flatMap(p => p.authors ?? []),
            ...claimedPage.pendingResults.flatMap(d => (d.new ?? d.current)?.authors ?? []),
        ];
        authorsOnClaimedPapers.filter(isMe).forEach(a => {
            if (a.display_name) hints.add(a.display_name);
        });
    }

    return [...hints];
}

/**
 * Order a paper's authors for the "which author are you?" dropdown: the
 * author whose name has the least edit distance to any name hint comes
 * first, the rest follow alphabetically. Returns [{ author, index }] pairs,
 * `index` being the position in the original (unsorted) authors array.
 */
function orderAuthorsForClaim(authors) {
    const hints = myNameHints().map(h => h.trim().toLowerCase());
    const indexed = authors.map((author, index) => ({ author, index }));
    indexed.sort((x, y) => (x.author.display_name || '').localeCompare(y.author.display_name || ''));

    if (hints.length > 0) {
        const distance = (author) => {
            const name = (author.display_name || '').trim().toLowerCase();
            return Math.min(...hints.map(h => editDistance(name, h)));
        };
        let bestPos = 0;
        let bestDistance = distance(indexed[0].author);
        for (let i = 1; i < indexed.length; i++) {
            const d = distance(indexed[i].author);
            if (d < bestDistance) {
                bestDistance = d;
                bestPos = i;
            }
        }
        const [best] = indexed.splice(bestPos, 1);
        indexed.unshift(best);
    }

    return indexed;
}

/**
 * Bottom-section widget for a paper: a button that toggles between "Claim"
 * (opens an inline author picker) and "Not mine" (immediate, no
 * confirmation). Either action keeps the paper right where it is -- it just
 * flips the button -- rather than re-running the search and possibly moving
 * the paper to the other section.
 */
function createClaimToggle(paper, claimed) {
    const container = html`<div class="my-papers-actions"></div>`;
    let currentPaper = paper;

    function showUnclaimButton() {
        container.innerHTML = '';
        const btn = html`<button type="button" class="btn-unclaim"><loc>Not mine</loc></button>`;
        btn.addEventListener('click', doUnclaim);
        container.appendChild(btn);
    }

    function showClaimButton() {
        container.innerHTML = '';
        const btn = html`<button type="button" class="btn-claim"><loc>Claim</loc></button>`;
        btn.addEventListener('click', showAuthorPicker);
        container.appendChild(btn);
    }

    async function doUnclaim() {
        const btn = container.querySelector('button');
        if (btn) btn.disabled = true;
        try {
            const updated = JSON.parse(JSON.stringify(currentPaper));
            const matches = (updated.authors ?? []).filter(isMe);
            if (matches.length === 0) {
                showToast(getTranslation('Nothing to unclaim'), 'error');
                return;
            }
            matches.forEach(a => { a.author.email = 'n/a'; });
            await submitPaper(updated, getTranslation('Unclaimed via My Papers'), suggestMode);
            currentPaper = updated;
            if (suggestMode) {
                // Only the suggestions db reflects this yet -- see
                // `reconcileLocallyUnclaimed` above.
                setLocallyUnclaimed(userEmail, currentPaper.id, true);
            }
            showToast(getTranslation('Paper unclaimed'), 'success');
            showClaimButton();
        } catch (error) {
            console.error('Failed to unclaim:', error);
            showToast(getTranslation('Failed to unclaim: {1}').replace('{1}', error.message), 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function showAuthorPicker() {
        const authors = currentPaper.authors ?? [];
        if (authors.length === 0) {
            showToast(getTranslation('This paper has no authors to claim'), 'error');
            return;
        }

        const select = html`<select class="claim-author-select"></select>`;
        orderAuthorsForClaim(authors).forEach(({ author: a, index }) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = a.display_name || `Author ${index + 1}`;
            select.appendChild(option);
        });

        const confirmBtn = html`<button type="button" class="btn-claim-confirm"><loc>Confirm</loc></button>`;
        const cancelBtn = html`<button type="button" class="btn-claim-cancel"><loc>Cancel</loc></button>`;

        confirmBtn.addEventListener('click', async () => {
            const index = parseInt(select.value, 10);
            confirmBtn.disabled = true;
            try {
                const updated = JSON.parse(JSON.stringify(currentPaper));
                updated.authors[index].author.email = userEmail;
                await submitPaper(updated, getTranslation('Claimed via My Papers'), suggestMode);
                currentPaper = updated;
                setLocallyUnclaimed(userEmail, currentPaper.id, false);
                showToast(getTranslation('Paper claimed'), 'success');
                showUnclaimButton();
            } catch (error) {
                console.error('Failed to claim:', error);
                showToast(getTranslation('Failed to claim: {1}').replace('{1}', error.message), 'error');
                confirmBtn.disabled = false;
            }
        });
        cancelBtn.addEventListener('click', showClaimButton);

        container.innerHTML = '';
        container.appendChild(html`<span class="claim-prompt"><loc>Which author are you?</loc></span>`);
        container.appendChild(select);
        container.appendChild(confirmBtn);
        container.appendChild(cancelBtn);
    }

    (claimed ? showUnclaimButton : showClaimButton)();
    return container;
}

function createPaginationControls(data, onPageChange, showTotalFound = false) {
    const { offset, count, total, validatedTotal, pendingTotal, next_offset: nextOffset } = data;
    const start = offset + 1;
    const end = offset + count;
    const paperWord = validatedTotal !== 1 ? 'papers' : 'paper';

    const prevButton = html`<button disabled="${offset === 0}"><loc>Previous</loc></button>`;
    prevButton.onclick = () => onPageChange(Math.max(0, offset - PAGE_SIZE));

    const nextButton = html`<button disabled="${nextOffset === null}"><loc>Next</loc></button>`;
    nextButton.onclick = () => {
        if (nextOffset !== null) onPageChange(nextOffset);
    };

    const pendingCount = pendingTotal
        ? html`<span class="pending-extra-count"> + <loc><span class="count">${pendingTotal}</span> pending</loc></span>`
        : null;
    const totalFoundInfo = showTotalFound
        ? html`<div class="results-info"><loc><span class="count">${validatedTotal}</span> ${paperWord} found</loc>${pendingCount}</div>`
        : html`<div></div>`;

    return html`
        <div class="pagination">
            ${totalFoundInfo}
            ${prevButton}
            <div class="page-info"><loc>Showing <span>${start}-${end}</span> of <span>${total}</span></loc></div>
            ${nextButton}
        </div>
    `;
}

function renderLoading(container) {
    container.innerHTML = '';
    container.appendChild(html`<div class="loading"><loc>Loading...</loc></div>`);
}

function renderError(container, error) {
    console.error('My papers search failed:', error);
    container.innerHTML = '';
    container.appendChild(html`<div class="error-message"><loc>Error loading results: <span>${error.message}</span></loc></div>`);
}

/**
 * Render one page of results (validated list, then a "Pending papers and
 * edits" tail, plus top/bottom pagination) into `container`. `data` carries
 * the raw (server-reported) counts used for the pagination controls, which
 * may not exactly match `validatedResults`/`pendingResults` when the caller
 * has filtered some items out client-side (see the "Unclaimed papers"
 * section below).
 */
function renderResultsInto(container, { data, validatedResults, pendingResults, bottomSectionFor, noResultsKey, onPageChange }) {
    container.innerHTML = '';
    const frag = document.createDocumentFragment();

    if (data.count === 0) {
        frag.appendChild(html`<div class="no-results"><loc>${noResultsKey}</loc></div>`);
    } else {
        frag.appendChild(createPaginationControls(data, onPageChange, true));
        if (validatedResults.length > 0) {
            const items = validatedResults.map(paper => createPaperResultElement(paper, {
                bottomSection: bottomSectionFor(paper),
                showEditIcon: true,
                searchParams: { author: currentAuthor },
            }));
            frag.appendChild(html`<ul class="paper-list">${items}</ul>`);
        }
        if (pendingResults.length > 0) {
            frag.appendChild(html`<h2 class="pending-results-header"><loc>Pending papers and edits</loc></h2>`);
            const items = pendingResults.map(diff => createPendingItem(diff, {
                showScore: false,
                showActions: false,
            }));
            frag.appendChild(html`<div class="workset-list pending-results-list">${items}</div>`);
        }
        if (data.total > PAGE_SIZE) {
            frag.appendChild(createPaginationControls(data, onPageChange));
        }
    }

    container.appendChild(frag);
    setLanguageNode(container);
}

function claimedIdsSet() {
    if (!claimedPage) return new Set();
    return new Set([
        ...claimedPage.validatedResults.map(p => p.id).filter(id => id != null),
        ...claimedPage.pendingResults.map(pendingId).filter(id => id != null),
    ]);
}

function renderClaimedSection(data) {
    // The author-name filter is applied here, client-side, on top of the
    // already-fetched (email-matched) page -- see `currentAuthor` above.
    renderResultsInto(document.getElementById('claimedSection'), {
        data,
        validatedResults: data.validatedResults.filter(p => paperMatchesAuthor(p, currentAuthor)),
        pendingResults: data.pendingResults.filter(d => pendingMatchesAuthor(d, currentAuthor)),
        bottomSectionFor: (paper) => createClaimToggle(paper, true),
        noResultsKey: 'No papers found for your account.',
        onPageChange: loadClaimed,
    });
}

// The claimed section's totals (validatedTotal/pendingTotal are true,
// server-reported counts across every page, not just the current one) are
// subtracted from the unclaimed section's raw totals, since every claimed
// paper is necessarily also a title match. This keeps "X papers found"
// accurate without an extra query.
//
// That subset guarantee breaks once an author-name filter is active though:
// the claimed total still counts every paper matched by email regardless of
// name, while the unclaimed total is now matched by name (fuzzy), so the two
// sets are no longer nested. Rather than risk an incorrect (or negative)
// subtraction, skip it in that case and show the raw unclaimed totals.
function subtractClaimedCounts(data) {
    if (currentAuthor) return data;

    const claimedValidatedTotal = claimedPage?.validatedTotal ?? 0;
    const claimedPendingTotal = claimedPage?.pendingTotal ?? 0;
    const validatedTotal = Math.max(0, (data.validatedTotal ?? 0) - claimedValidatedTotal);
    const pendingTotal = data.pendingTotal != null
        ? Math.max(0, data.pendingTotal - claimedPendingTotal)
        : null;
    return {
        ...data,
        validatedTotal,
        pendingTotal,
        total: validatedTotal + (pendingTotal ?? 0),
    };
}

// The "Unclaimed papers" section excludes whatever is currently displayed in
// the claimed section, so the same paper isn't shown twice on screen. That
// exclusion set only reflects the claimed section's *current page* (not every
// claimed paper) so that paginating one section never requires re-querying
// the other.
function renderUnclaimedSection(data) {
    const wrapper = document.getElementById('unclaimedWrapper');
    wrapper.style.display = '';

    const excluded = claimedIdsSet();
    const validatedResults = data.validatedResults.filter(p => p.id == null || !excluded.has(p.id));
    const pendingResults = data.pendingResults.filter(diff => {
        const id = pendingId(diff);
        return id == null || !excluded.has(id);
    });

    renderResultsInto(document.getElementById('unclaimedSection'), {
        data: subtractClaimedCounts(data),
        validatedResults,
        pendingResults,
        bottomSectionFor: (paper) => createClaimToggle(paper, false),
        noResultsKey: 'No unclaimed papers found.',
        onPageChange: loadUnclaimed,
    });
}

function goToNewPaper() {
    window.open(`/edit/new${suggestMode ? '?suggest=1' : ''}`, '_blank');
}

// The "Add Paper" button only makes sense once a title has been searched
// for (the new paper's title starts from that search box); until then it's
// disabled with an explanatory hint next to it.
function updateAddPaperButton() {
    const btn = document.getElementById('addPaperBtn');
    const hint = document.getElementById('addPaperHint');
    if (!btn) return;
    const enabled = !!currentTitle;
    btn.disabled = !enabled;
    if (hint) hint.style.display = enabled ? 'none' : '';
}

function ensureSections() {
    const container = document.getElementById('resultsContainer');
    if (document.getElementById('claimedSection')) return;

    container.innerHTML = '';
    container.appendChild(html`<div id="claimedSection"></div>`);

    const addPaperBar = html`
        <div class="add-paper-bar">
            <button type="button" id="addPaperBtn" class="btn-add-paper" disabled><loc>Add Paper</loc></button>
            <span id="addPaperHint" class="add-paper-hint"><loc>Search by title first</loc></span>
        </div>
    `;
    addPaperBar.querySelector('#addPaperBtn').addEventListener('click', goToNewPaper);
    container.appendChild(addPaperBar);

    container.appendChild(html`
        <div id="unclaimedWrapper" style="display: none;">
            <h2 class="my-papers-section-header"><loc>Unclaimed papers</loc></h2>
            <div id="unclaimedSection"></div>
        </div>
    `);
}

function clearUnclaimedSection() {
    const wrapper = document.getElementById('unclaimedWrapper');
    if (wrapper) wrapper.style.display = 'none';
    const section = document.getElementById('unclaimedSection');
    if (section) section.innerHTML = '';
}

async function loadClaimed(offset) {
    ensureSections();
    const container = document.getElementById('claimedSection');
    renderLoading(container);
    try {
        const data = await fetchPage({ title: currentTitle, author: userEmail }, offset);
        data.validatedResults = await reconcileLocallyUnclaimed(data.validatedResults);
        claimedPage = data;
        renderClaimedSection(data);
        // The exclusion set the unclaimed section uses just changed: re-apply
        // it to the already-fetched unclaimed page instead of re-querying.
        if (unclaimedRawPage) {
            renderUnclaimedSection(unclaimedRawPage);
        }
    } catch (error) {
        renderError(container, error);
    }
}

// The "Unclaimed papers" section runs off of a plain title/author search, so
// it's only meaningful once at least one of those is filled in -- but either
// one alone is enough (title search on its own already worked; an
// author-only search was being skipped, which was the bug).
function hasSearchCriteria() {
    return !!(currentTitle || currentAuthor);
}

async function loadUnclaimed(offset) {
    ensureSections();
    if (!hasSearchCriteria()) {
        clearUnclaimedSection();
        unclaimedRawPage = null;
        return;
    }

    const wrapper = document.getElementById('unclaimedWrapper');
    wrapper.style.display = '';
    const container = document.getElementById('unclaimedSection');
    renderLoading(container);
    try {
        // Unlike the claimed section, nothing here needs the `author` slot
        // for an email match, so the author-name filter can just be passed
        // straight through to the API.
        const data = await fetchPage({ title: currentTitle, author: currentAuthor }, offset);
        unclaimedRawPage = data;
        renderUnclaimedSection(data);
    } catch (error) {
        renderError(container, error);
    }
}

// Unclaimed papers are only shown once the claimed section has finished
// loading -- both because the exclusion set they're filtered against isn't
// known until then, and so the two sections don't visibly race each other.
async function runSearch() {
    claimedPage = null;
    unclaimedRawPage = null;
    ensureSections();
    clearUnclaimedSection();
    updateAddPaperButton();

    await loadClaimed(0);

    if (hasSearchCriteria()) {
        loadUnclaimed(0);
    }
}

/**
 * Read the "claim-for" URL parameter and set up the editable "Claiming for
 * <email>" field. Defaults to the logged-in user's email, but a URL
 * parameter or a manual edit can point the page at a different email.
 */
function initClaimForBar() {
    const urlParams = new URLSearchParams(window.location.search);
    userEmail = (urlParams.get('claim-for') || loginEmail || '').trim();

    const span = document.getElementById('claimForEmail');
    span.textContent = userEmail;

    function startEditing() {
        const input = document.createElement('input');
        input.type = 'email';
        input.className = 'claim-for-input';
        input.value = userEmail;
        span.replaceWith(input);
        input.focus();
        input.select();

        function commit() {
            const value = input.value.trim() || loginEmail;
            input.replaceWith(span);
            span.textContent = value;
            if (value !== userEmail) {
                userEmail = value;
                updateClaimForUrl(value);
                runSearch();
            }
        }

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
            } else if (e.key === 'Escape') {
                input.value = userEmail;
                input.blur();
            }
        });
    }

    span.addEventListener('click', startEditing);
    span.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            startEditing();
        }
    });
}

function updateClaimForUrl(email) {
    const urlParams = new URLSearchParams(window.location.search);
    if (email && email !== loginEmail) {
        urlParams.set('claim-for', email);
    } else {
        urlParams.delete('claim-for');
    }
    const newUrl = urlParams.toString()
        ? `${window.location.pathname}?${urlParams.toString()}`
        : window.location.pathname;
    window.history.replaceState({}, '', newUrl);
}

export function displayMyPapers(email, suggest) {
    loginEmail = email;
    suggestMode = suggest;

    initClaimForBar();

    const form = document.getElementById('myPapersForm');
    const titleInput = document.getElementById('title');
    const authorInput = document.getElementById('author');
    const clearButton = document.getElementById('clearSearch');

    form.addEventListener('submit', (e) => e.preventDefault());

    const debouncedSearch = debounce(() => {
        currentTitle = titleInput.value.trim();
        currentAuthor = authorInput.value.trim();
        runSearch();
    }, 300);

    titleInput.addEventListener('input', debouncedSearch);
    authorInput.addEventListener('input', debouncedSearch);

    clearButton.addEventListener('click', () => {
        titleInput.value = '';
        authorInput.value = '';
        currentTitle = '';
        currentAuthor = '';
        runSearch();
    });

    runSearch();
}
