import { html } from './common.js';
import { createPaperElement } from './paper.js';

const PAGE_SIZE = 200;

let isValidator = false;
let defaults = {
    defaultNdays: 30,
    defaultFwd: 0,
    defaultSerial: 0
};

function setResults(...elements) {
    const container = document.getElementById('resultsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function addDays(dateStr, days) {
    const date = new Date(dateStr);
    date.setDate(date.getDate() + days);
    return formatDate(date);
}

function subtractDays(dateStr, days) {
    const date = new Date(dateStr);
    date.setDate(date.getDate() - days);
    return formatDate(date);
}

async function fetchSearchResults(startDate, endDate) {
    const queryParams = new URLSearchParams({
        offset: '0',
        size: PAGE_SIZE.toString(),
        expand_links: 'true',
        start_date: startDate,
        end_date: endDate
    });

    const url = `/api/v1/search?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function filterPapersBySerial(papers, minSerial) {
    if (minSerial <= 0) {
        return papers;
    }
    
    return papers.filter(paper => {
        const latestSerial = paper.info?.latest_serial;
        // Keep paper if latest_serial is defined and >= minSerial
        // Filter out papers where latest_serial < minSerial or undefined
        if (latestSerial === undefined || latestSerial === null) {
            return true;
        }
        return latestSerial >= minSerial;
    });
}

function createResultsInfo(filteredCount, totalCount, startDate, endDate, minSerial) {
    const paperWord = filteredCount !== 1 ? 'papers' : 'paper';
    
    let filterInfo = '';
    if (minSerial > 0 && filteredCount !== totalCount) {
        filterInfo = ` (filtered from ${totalCount} by serial ≥ ${minSerial})`;
    }
    
    return html`
        <div class="results-info">
            <span class="count">${filteredCount}</span> ${paperWord} found${filterInfo} between ${startDate} and ${endDate}
        </div>
    `;
}

function displayResults(papers, totalCount, startDate, endDate, minSerial) {
    if (papers.length === 0) {
        const noResults = html`
            <div class="no-results">
                No papers found matching the criteria.
            </div>
        `;
        setResults(noResults);
        return;
    }

    const resultsInfo = createResultsInfo(papers.length, totalCount, startDate, endDate, minSerial);

    const paperElements = papers.map(paper => createPaperElement(paper, {
        showEditIcon: isValidator
    }));
    const paperList = html`<ul class="paper-list">${paperElements}</ul>`;

    setResults(resultsInfo, paperList);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading results: ${error.message}</div>`);
}

function updateUrlParams(params) {
    const urlParams = new URLSearchParams();
    
    if (params.date) urlParams.set('date', params.date);
    if (params.ndays !== defaults.defaultNdays) urlParams.set('ndays', params.ndays.toString());
    if (params.fwd !== defaults.defaultFwd) urlParams.set('fwd', params.fwd.toString());
    if (params.serial !== defaults.defaultSerial) urlParams.set('serial', params.serial.toString());

    const newUrl = urlParams.toString() 
        ? `${window.location.pathname}?${urlParams.toString()}`
        : window.location.pathname;
    
    window.history.replaceState({}, '', newUrl);
}

async function performSearch(params) {
    updateUrlParams(params);
    displayLoading();

    try {
        const startDate = subtractDays(params.date, params.ndays);
        const endDate = addDays(params.date, params.fwd);

        const data = await fetchSearchResults(startDate, endDate);
        const filteredPapers = filterPapersBySerial(data.results, params.serial);
        displayResults(filteredPapers, data.results.length, startDate, endDate, params.serial);
    } catch (error) {
        console.error('Search failed:', error);
        displayError(error);
    }
}

export function latestGroup(hasValidateCapability = false, options = {}) {
    isValidator = hasValidateCapability;
    defaults = { ...defaults, ...options };

    const form = document.getElementById('latestGroupForm');
    const dateInput = document.getElementById('date');
    const ndaysInput = document.getElementById('ndays');
    const fwdInput = document.getElementById('fwd');
    const serialInput = document.getElementById('serial');

    // Set default date to today
    const today = formatDate(new Date());
    dateInput.value = today;

    // Read URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const initialParams = {
        date: urlParams.get('date') || today,
        ndays: parseInt(urlParams.get('ndays') || defaults.defaultNdays.toString(), 10),
        fwd: parseInt(urlParams.get('fwd') || defaults.defaultFwd.toString(), 10),
        serial: parseInt(urlParams.get('serial') || defaults.defaultSerial.toString(), 10)
    };

    // Set form values from URL parameters or defaults
    dateInput.value = initialParams.date;
    ndaysInput.value = initialParams.ndays;
    fwdInput.value = initialParams.fwd;
    serialInput.value = initialParams.serial;

    function getFormParams() {
        return {
            date: dateInput.value || today,
            ndays: parseInt(ndaysInput.value, 10) || 0,
            fwd: parseInt(fwdInput.value, 10) || 0,
            serial: parseInt(serialInput.value, 10) || 0
        };
    }

    // Handle form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        performSearch(getFormParams());
    });

    // Perform initial search
    performSearch(initialParams);
}
