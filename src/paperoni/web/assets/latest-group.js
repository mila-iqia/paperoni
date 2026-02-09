import { html } from './common.js';
import { createPaperElement } from './paper.js';

let isValidator = false;
let defaults = {
    defaultNdays: 30,
    defaultFwd: 0,
    defaultSerial: 0
};

let activeTab = 'peer-reviewed';

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

function formatDatetimeLocal(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function datetimeLocalToTimestamp(value) {
    if (!value) return 0;
    const date = new Date(value);
    return Math.floor(date.getTime() / 1000);
}

function timestampToDatetimeLocal(timestamp) {
    if (timestamp === null || timestamp === undefined || timestamp === 0 || isNaN(timestamp)) return '';
    const date = new Date(timestamp * 1000);
    return formatDatetimeLocal(date);
}

function buildQueryParams(params) {
    return new URLSearchParams({
        back: params.ndays.toString(),
        forward: params.fwd.toString(),
        serial: params.serial.toString(),
        date: params.date
    });
}

async function fetchLatest(params) {
    const queryParams = buildQueryParams(params);
    const url = `/api/v1/latest?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

async function generateNewsletter(params) {
    const queryParams = buildQueryParams(params);
    const url = `/latest-group/generate?${queryParams.toString()}`;
    const response = await fetch(url, { method: 'POST' });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function createPaperList(papers) {
    if (papers.length === 0) {
        return html`
            <div class="no-results">
                No papers found in this category.
            </div>
        `;
    }

    const paperElements = papers.map(paper => createPaperElement(paper, {
        showEditIcon: isValidator
    }));
    return html`<ul class="paper-list">${paperElements}</ul>`;
}

function displayResults(data) {
    const peerReviewed = data['peer-reviewed'] || [];
    const preprints = data['preprints'] || [];

    const tabContent = {
        'peer-reviewed': peerReviewed,
        'preprints': preprints
    };

    // Create the container
    const container = html`
        <div class="latest-tabs-container">
            <div class="latest-tabs">
                <button class="latest-tab-button ${activeTab === 'peer-reviewed' ? 'active' : ''}" data-tab="peer-reviewed">
                    Peer-Reviewed <span class="latest-tab-count">(${peerReviewed.length})</span>
                </button>
                <button class="latest-tab-button ${activeTab === 'preprints' ? 'active' : ''}" data-tab="preprints">
                    Preprints <span class="latest-tab-count">(${preprints.length})</span>
                </button>
            </div>
            <div class="latest-tab-content"></div>
        </div>
    `;

    // Get references to elements
    const tabButtons = container.querySelectorAll('.latest-tab-button');
    const contentDiv = container.querySelector('.latest-tab-content');

    // Function to render content for a tab
    function renderTab(tab) {
        contentDiv.innerHTML = '';
        contentDiv.appendChild(createPaperList(tabContent[tab]));
    }

    // Add click handlers
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            button.classList.add('active');
            activeTab = button.dataset.tab;
            renderTab(activeTab);
        });
    });

    // Render the initial tab content
    renderTab(activeTab);

    setResults(container);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error: ${error.message}</div>`);
}

function displayGeneratedLinks(links) {
    const container = document.getElementById('linksContainer');
    container.innerHTML = '';

    if (!links || Object.keys(links).length === 0) {
        container.appendChild(html`<div class="no-results">No links generated.</div>`);
        return;
    }

    const linksList = html`
        <div class="generated-links">
            <h3>Generated Newsletter Links</h3>
            <ul class="links-list">
                ${Object.entries(links).map(([title, urls]) => html`
                    <li class="link-item">
                        <span class="link-title">${title}</span>
                        <div class="link-urls">
                            <a href="${urls.url}" target="_blank" rel="noopener noreferrer" class="link-main">View</a>
                            ${urls.archive ? html`<a href="${urls.archive}" target="_blank" rel="noopener noreferrer" class="link-archive">Archive</a>` : ''}
                        </div>
                    </li>
                `)}
            </ul>
        </div>
    `;

    container.appendChild(linksList);
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
        const data = await fetchLatest(params);
        displayResults(data);
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
    const now = Math.floor(Date.now() / 1000);
    const defaultSerial = defaults.defaultSerial || now;
    const initialSerial = urlParams.has('serial') 
        ? parseInt(urlParams.get('serial'), 10) 
        : defaultSerial;
    const initialParams = {
        date: urlParams.get('date') || today,
        ndays: parseInt(urlParams.get('ndays') || defaults.defaultNdays.toString(), 10),
        fwd: parseInt(urlParams.get('fwd') || defaults.defaultFwd.toString(), 10),
        serial: initialSerial
    };

    // Set form values from URL parameters or defaults
    dateInput.value = initialParams.date;
    ndaysInput.value = initialParams.ndays;
    fwdInput.value = initialParams.fwd;
    serialInput.value = timestampToDatetimeLocal(initialSerial);

    function getFormParams() {
        return {
            date: dateInput.value || today,
            ndays: parseInt(ndaysInput.value, 10) || 0,
            fwd: parseInt(fwdInput.value, 10) || 0,
            serial: datetimeLocalToTimestamp(serialInput.value)
        };
    }

    // Handle form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        performSearch(getFormParams());
    });

    // Handle generate button
    const generateBtn = document.getElementById('generateBtn');
    const linksContainer = document.getElementById('linksContainer');
    generateBtn.addEventListener('click', async () => {
        const params = getFormParams();
        generateBtn.disabled = true;
        generateBtn.textContent = 'Generating...';
        linksContainer.innerHTML = '';
        try {
            const result = await generateNewsletter(params);
            console.log('Generate result:', result);
            if (result.status === 'failure') {
                displayError(new Error(result.reason || 'Unknown error'));
            } else {
                displayGeneratedLinks(result.links);
            }
        } catch (error) {
            console.error('Generate failed:', error);
            displayError(error);
        } finally {
            generateBtn.disabled = false;
            generateBtn.textContent = 'Generate';
        }
    });

    // Perform initial search
    performSearch(initialParams);
}
