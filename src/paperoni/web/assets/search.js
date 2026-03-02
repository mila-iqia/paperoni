import { debounce, html } from './common.js';
import { createPaperElement, createScoreBand } from './paper.js';
import { createWorksetElement } from './workset.js';
import { appendSearchParamsTo, clearSearchForm, getSearchParams } from './search-form.js';

const PAGE_SIZE = 50;

let currentOffset = 0;
let currentParams = {};
let totalResults = 0;
let isValidator = false;
let showScores = false;
let useDevMode = false;

function setResults(...elements) {
    const container = document.getElementById('resultsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

async function fetchSearchResults(params, offset = 0) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: PAGE_SIZE.toString(),
        expand_links: 'true'
    });
    appendSearchParamsTo(queryParams, params);

    const url = `/api/v1/search?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function createPagination(offset, count, total, nextOffset, showTotalFound = false) {
    const start = offset + 1;
    const end = offset + count;
    const paperWord = total !== 1 ? 'papers' : 'paper';

    const prevButton = html`<button disabled="${offset === 0}">Previous</button>`;
    prevButton.onclick = () => {
        const newOffset = Math.max(0, offset - PAGE_SIZE);
        performSearch(currentParams, newOffset);
    };

    const nextButton = html`<button disabled="${nextOffset === null}">Next</button>`;
    nextButton.onclick = () => {
        if (nextOffset !== null) {
            performSearch(currentParams, nextOffset);
        }
    };

    const totalFoundInfo = showTotalFound
        ? html`<div class="results-info"><span class="count">${total}</span> ${paperWord} found</div>`
        : html`<div></div>`;

    return html`
        <div class="pagination">
            ${totalFoundInfo}
            ${prevButton}
            <div class="page-info">Showing ${start}-${end} of ${total}</div>
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
    totalResults = data.total;

    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                No papers found. Try adjusting your search criteria.
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
            showEditIcon: isValidator,
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
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading results: ${error.message}</div>`);
}

function updateUrlParams(params, offset) {
    const urlParams = new URLSearchParams();
    
    if (params.title) urlParams.set('title', params.title);
    if (params.author) urlParams.set('author', params.author);
    if (params.institution) urlParams.set('institution', params.institution);
    if (params.venue) urlParams.set('venue', params.venue);
    if (params.start_date) urlParams.set('start_date', params.start_date);
    if (params.end_date) urlParams.set('end_date', params.end_date);
    if (params.peerReviewed) urlParams.set('peerReviewed', 'true');
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

export function searchPapers(hasValidateCapability = false, enableScores = false, enableDevMode = false) {
    isValidator = hasValidateCapability;
    showScores = enableScores;
    useDevMode = enableDevMode;

    const form = document.getElementById('searchForm');
    const titleInput = document.getElementById('title');
    const authorInput = document.getElementById('author');
    const institutionInput = document.getElementById('institution');
    const venueInput = document.getElementById('venue');
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    const peerReviewedCheckbox = document.getElementById('peerReviewed');

    function handleInputChange() {
        debouncedSearch(getSearchParams());
    }

    titleInput.addEventListener('input', handleInputChange);
    authorInput.addEventListener('input', handleInputChange);
    institutionInput.addEventListener('input', handleInputChange);
    venueInput.addEventListener('input', handleInputChange);
    startDateInput.addEventListener('input', handleInputChange);
    endDateInput.addEventListener('input', handleInputChange);
    peerReviewedCheckbox.addEventListener('change', handleInputChange);

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

    // Perform initial search if URL has parameters
    const urlParams = new URLSearchParams(window.location.search);
    const initialParams = {
        title: urlParams.get('title') || '',
        author: urlParams.get('author') || '',
        institution: urlParams.get('institution') || '',
        venue: urlParams.get('venue') || '',
        start_date: urlParams.get('start_date') || '',
        end_date: urlParams.get('end_date') || '',
        peerReviewed: urlParams.get('peerReviewed') === 'true'
    };
    const initialOffset = parseInt(urlParams.get('offset') || '0', 10);

    // Set form values from URL parameters
    titleInput.value = initialParams.title;
    authorInput.value = initialParams.author;
    institutionInput.value = initialParams.institution;
    venueInput.value = initialParams.venue;
    startDateInput.value = initialParams.start_date;
    endDateInput.value = initialParams.end_date;
    peerReviewedCheckbox.checked = initialParams.peerReviewed;

    // Always perform initial search, even with empty criteria
    performSearch(initialParams, initialOffset);
}
