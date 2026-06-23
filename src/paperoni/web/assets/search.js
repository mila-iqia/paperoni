import { debounce, html, showToast } from './common.js';
import { setLanguageNode } from './translate.js';
import { createPaperElement, createScoreBand, formatRelease, matchesSearch } from './paper.js';
import { createWorksetElement } from './workset.js';
import { appendSearchParamsTo, clearSearchForm, getSearchParams, setupPeerReviewedShortcut, syncPeerReviewedCheckbox } from './search-form.js';

const PAGE_SIZE = 50;

let currentOffset = 0;
let currentParams = {};
let showEditIcon = false;
let showScores = false;
let useDevMode = false;

function setResults(...elements) {
    const container = document.getElementById('resultsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
    setLanguageNode(container);
}

async function fetchSearchResults(params, offset = 0, limit = PAGE_SIZE, signal = null) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
        expand_links: 'true'
    });
    appendSearchParamsTo(queryParams, params);

    const url = `/api/v1/search?${queryParams.toString()}`;
    const response = await fetch(url, signal ? { signal } : undefined);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

const EXPORT_PAGE_SIZE = 100;
const EXPORT_DELAY_MS = 50;

// Abortable sleep: rejects with an AbortError if the signal fires while waiting.
function sleep(ms, signal = null) {
    return new Promise((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
        }
        const timer = setTimeout(resolve, ms);
        signal?.addEventListener('abort', () => {
            clearTimeout(timer);
            reject(new DOMException('Aborted', 'AbortError'));
        }, { once: true });
    });
}

// The export currently in flight (if any), so its button can cancel it.
let activeExport = null;

/**
 * Iterate over every page of the current search via the API and collect all
 * results. Requests are throttled to one per EXPORT_DELAY_MS, but if a request
 * itself takes longer than that we don't add any extra wait. Cancellable via
 * the AbortSignal.
 */
async function fetchAllResults(params, signal, onProgress) {
    const results = [];
    let offset = 0;

    while (true) {
        const start = performance.now();
        const data = await fetchSearchResults(params, offset, EXPORT_PAGE_SIZE, signal);
        results.push(...data.results);

        if (onProgress) onProgress(results.length, data.total);

        if (data.next_offset === null || data.next_offset === undefined) {
            break;
        }
        offset = data.next_offset;

        // Only wait if the request was faster than the throttle interval.
        const elapsed = performance.now() - start;
        if (elapsed < EXPORT_DELAY_MS) {
            await sleep(EXPORT_DELAY_MS - elapsed, signal);
        }
    }
    return results;
}

function downloadFile(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = html`<a href="${url}" download="${filename}"></a>`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function csvEscape(value) {
    const s = value == null ? '' : String(value);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// Mirror the backend venue search: match against the venue name, short name,
// and aliases (case-insensitive substring).
function releaseMatchesVenue(release, venueSearch) {
    const v = release.venue;
    if (!v) return false;
    return matchesSearch(v.name, venueSearch)
        || matchesSearch(v.short_name, venueSearch)
        || (v.aliases ?? []).some(a => matchesSearch(a, venueSearch));
}

/**
 * Build a CSV from search results. For each paper, status/venue/date come from
 * the first release matching the searched venue (or release 0 when no venue was
 * searched). Papers with no releases are skipped.
 */
function resultsToCsv(results, params) {
    const venueSearch = (params.venue ?? '').trim();
    const headers = ['title', 'authors', 'status', 'venue', 'date', 'abstract_link', 'pdf_link'];
    const rows = [headers];

    for (const paper of results) {
        const releases = paper.releases ?? [];
        if (releases.length === 0) continue;

        const release = venueSearch
            ? (releases.find(r => releaseMatchesVenue(r, venueSearch)) ?? releases[0])
            : releases[0];
        const { date, venueName, status } = formatRelease(release);

        const authors = (paper.authors ?? [])
            .map(a => a.display_name ?? '')
            .filter(Boolean)
            .join(', ');

        const links = paper.links ?? [];
        const abstractLink = links.find(l => {
            const t = l.type?.toLowerCase() ?? '';
            return t.includes('abstract') || t.includes('html.official');
        })?.link ?? '';
        const pdfLink = links.find(l => l.type?.toLowerCase().includes('pdf'))?.link ?? '';

        rows.push([paper.title ?? '', authors, status ?? '', venueName ?? '', date ?? '', abstractLink, pdfLink]);
    }

    return rows.map(row => row.map(csvEscape).join(',')).join('\r\n');
}

/**
 * Run an export ("json" or "csv"). While running, the button shows live
 * progress (it has a fixed width so it doesn't jump around) and a little "x"
 * cancel control appears to its right (its space is always reserved so nothing
 * shifts). The other export button is disabled meanwhile.
 */
async function runExport(exp, others, params) {
    if (activeExport) return;

    const controller = new AbortController();
    activeExport = { controller, exp };

    const originalText = exp.button.textContent;
    exp.cancel?.classList.add('visible');
    others.forEach(o => { if (o.button) o.button.disabled = true; });

    const setProgress = (n, total) => {
        exp.button.textContent = `${n}/${total}`;
    };
    setProgress(0, '…');

    try {
        const results = await fetchAllResults(params, controller.signal, setProgress);

        if (exp.kind === 'csv') {
            const BOM = String.fromCharCode(0xFEFF); // helps Excel detect UTF-8
            downloadFile(BOM + resultsToCsv(results, params), 'papers.csv', 'text/csv;charset=utf-8');
        } else {
            downloadFile(JSON.stringify(results, null, 2), 'papers.json', 'application/json');
        }
        showToast(`Exported ${results.length} papers`, 'success');
    } catch (error) {
        if (error.name === 'AbortError') {
            showToast('Export cancelled', 'error');
        } else {
            console.error('Export failed:', error);
            showToast(`Export failed: ${error.message}`, 'error');
        }
    } finally {
        activeExport = null;
        exp.cancel?.classList.remove('visible');
        exp.button.textContent = originalText;
        others.forEach(o => { if (o.button) o.button.disabled = false; });
    }
}

// Wire up the export buttons (and their "x" cancel controls).
function wireExportButtons(getParams) {
    const exports = [
        { kind: 'json', button: document.getElementById('exportJson'), cancel: document.getElementById('exportJsonCancel') },
        { kind: 'csv', button: document.getElementById('exportCsv'), cancel: document.getElementById('exportCsvCancel') },
    ];

    exports.forEach(exp => {
        if (!exp.button) return;
        exp.button.addEventListener('click', () => {
            if (activeExport) return;
            runExport(exp, exports.filter(o => o !== exp), getParams());
        });
        exp.cancel?.addEventListener('click', () => {
            if (activeExport && activeExport.exp === exp) activeExport.controller.abort();
        });
    });
}

function createPagination(offset, count, total, nextOffset, showTotalFound = false) {
    const start = offset + 1;
    const end = offset + count;
    const paperWord = total !== 1 ? 'papers' : 'paper';

    const prevButton = html`<button disabled="${offset === 0}"><loc>Previous</loc></button>`;
    prevButton.onclick = () => {
        const newOffset = Math.max(0, offset - PAGE_SIZE);
        performSearch(currentParams, newOffset);
    };

    const nextButton = html`<button disabled="${nextOffset === null}"><loc>Next</loc></button>`;
    nextButton.onclick = () => {
        if (nextOffset !== null) {
            performSearch(currentParams, nextOffset);
        }
    };

    const totalFoundInfo = showTotalFound
        ? html`<div class="results-info"><loc><span class="count">${total}</span> ${paperWord} found</loc></div>`
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

// Click handlers for search filtering
function handleAuthorClick(authorName) {
    const authorInput = document.getElementById('author');
    if (authorInput) {
        authorInput.value = authorName;
        authorInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

function handleInstitutionClick(institutionName) {
    const institutionInput = document.getElementById('institution');
    if (institutionInput) {
        institutionInput.value = institutionName;
        institutionInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

function handleVenueClick(venueName) {
    const venueInput = document.getElementById('venue');
    if (venueInput) {
        venueInput.value = venueName;
        venueInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

function handleYearClick(year) {
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    if (startDateInput && endDateInput) {
        startDateInput.value = `${year}-01-01`;
        endDateInput.value = `${year}-12-31`;
        startDateInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

/**
 * Create a paper result element for display (used by search and pending).
 * @param {Object} paper - The paper object
 * @param {Object} options - Options: showScores, score, searchParams, onAuthorClick, etc.
 * @returns {HTMLElement} The paper element, optionally wrapped with score band
 */
export function createPaperResultElement(paper, options = {}) {
    const {
        showScores = false,
        score = 0,
        searchParams = {},
        onAuthorClick = null,
        onInstitutionClick = null,
        onVenueClick = null,
        onYearClick = null,
        bottomSection = null,
        showEditIcon = false,
    } = options;

    const paperEl = createPaperElement(paper, {
        searchParams,
        onAuthorClick,
        onInstitutionClick,
        onVenueClick,
        onYearClick,
        bottomSection,
        showEditIcon,
    });

    if (showScores) {
        return html`
            <li class="paper-item-with-score">
                ${createScoreBand(score)}
                <div class="paper-content-wrapper">${paperEl}</div>
            </li>
        `;
    }
    return paperEl;
}

function displayResults(data) {
    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                <loc>No papers found. Try adjusting your search criteria.</loc>
            </div>
        `;
        setResults(noResults);
        return;
    }

    const paginationTop = createPagination(data.offset ?? currentOffset, data.count, data.total, data.next_offset, true);

    const paperElements = data.results.map(paper => {
        if (useDevMode) {
            const fakeWorkset = { score: paper.score, value: { current: paper, collected: [] } };
            return createWorksetElement(fakeWorkset);
        }
        return createPaperResultElement(paper, {
            showScores,
            score: paper.score ?? 0,
            searchParams: currentParams,
            onAuthorClick: handleAuthorClick,
            onInstitutionClick: handleInstitutionClick,
            onVenueClick: handleVenueClick,
            onYearClick: handleYearClick,
            bottomSection: null,
            showEditIcon: showEditIcon,
        });
    });
    const paperList = useDevMode
        ? html`<div class="workset-list">${paperElements}</div>`
        : html`<ul class="paper-list">${paperElements}</ul>`;

    const paginationBottom = data.total > PAGE_SIZE
        ? createPagination(data.offset ?? currentOffset, data.count, data.total, data.next_offset)
        : null;

    setResults(paginationTop, paperList, paginationBottom);
}

function displayLoading() {
    setResults(html`<div class="loading"><loc>Loading...</loc></div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message"><loc>Error loading results: <span>${error.message}</span></loc></div>`);
}

function updateUrlParams(params, offset) {
    const urlParams = new URLSearchParams();
    
    if (params.title) urlParams.set('title', params.title);
    if (params.author) urlParams.set('author', params.author);
    if (params.institution) urlParams.set('institution', params.institution);
    if (params.venue) urlParams.set('venue', params.venue);
    if (params.status && params.status.length) urlParams.set('status', params.status.join(', '));
    if (params.start_date) urlParams.set('start_date', params.start_date);
    if (params.end_date) urlParams.set('end_date', params.end_date);
    if (offset > 0) urlParams.set('offset', offset.toString());
    if (useDevMode) urlParams.set('dev', '');

    const newUrl = urlParams.toString() 
        ? `${window.location.pathname}?${urlParams.toString()}`
        : window.location.pathname;
    
    window.history.replaceState({}, '', newUrl);
}

async function performSearch(params, offset = 0) {
    currentParams = params;
    currentOffset = offset;

    updateUrlParams(params, offset);
    displayLoading();

    try {
        const data = await fetchSearchResults(params, offset);
        displayResults(data);
    } catch (error) {
        console.error('Search failed:', error);
        displayError(error);
    }
}

const debouncedSearch = debounce((params) => {
    performSearch(params, 0);
}, 300);

export function searchPapers(editButton = true, enableScores = false, enableDevMode = false) {
    showEditIcon = editButton;
    showScores = enableScores;
    useDevMode = enableDevMode;

    const form = document.getElementById('searchForm');
    const titleInput = document.getElementById('title');
    const authorInput = document.getElementById('author');
    const institutionInput = document.getElementById('institution');
    const venueInput = document.getElementById('venue');
    const statusInput = document.getElementById('status');
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');

    function handleInputChange() {
        debouncedSearch(getSearchParams());
    }

    titleInput.addEventListener('input', handleInputChange);
    authorInput.addEventListener('input', handleInputChange);
    institutionInput.addEventListener('input', handleInputChange);
    venueInput.addEventListener('input', handleInputChange);
    statusInput.addEventListener('input', handleInputChange);
    startDateInput.addEventListener('input', handleInputChange);
    endDateInput.addEventListener('input', handleInputChange);
    // The "Peer reviewed" checkbox is a shortcut that toggles "peer-reviewed"
    // in the Type field rather than a separate filter.
    setupPeerReviewedShortcut(handleInputChange);

    // Prevent form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
    });

    // Clear search button
    const clearButton = document.getElementById('clearSearch');
    clearButton.addEventListener('click', () => {
        clearSearchForm();
        handleInputChange();
    });

    // Export buttons: iterate the whole result set via the API and download it.
    wireExportButtons(getSearchParams);

    // Perform initial search if URL has parameters
    const urlParams = new URLSearchParams(window.location.search);
    const initialStatusStr = urlParams.get('status') || '';
    const initialParams = {
        title: urlParams.get('title') || '',
        author: urlParams.get('author') || '',
        institution: urlParams.get('institution') || '',
        venue: urlParams.get('venue') || '',
        status: initialStatusStr.split(',').map((s) => s.trim()).filter((s) => s),
        start_date: urlParams.get('start_date') || '',
        end_date: urlParams.get('end_date') || '',
    };
    const initialOffset = parseInt(urlParams.get('offset') || '0', 10);

    // Set form values from URL parameters
    titleInput.value = initialParams.title;
    authorInput.value = initialParams.author;
    institutionInput.value = initialParams.institution;
    venueInput.value = initialParams.venue;
    statusInput.value = initialStatusStr;
    startDateInput.value = initialParams.start_date;
    endDateInput.value = initialParams.end_date;
    syncPeerReviewedCheckbox();

    // Always perform initial search, even with empty criteria
    performSearch(initialParams, initialOffset);
}
