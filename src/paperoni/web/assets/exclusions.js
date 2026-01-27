import { html } from './common.js';

/**
 * Show a toast notification in the bottom right
 */
function showToast(message, type = 'success') {
    const toast = html`
        <div class="toast toast-${type}">
            <span class="toast-message">${message}</span>
            <button class="toast-close" type="button">×</button>
        </div>
    `;

    // Add close functionality
    toast.querySelector('.toast-close').addEventListener('click', () => {
        toast.classList.add('toast-hiding');
        setTimeout(() => {
            toast.remove();
            updateToastPositions();
        }, 300);
    });

    // Add to page
    document.body.appendChild(toast);
    
    // Update positions of all toasts to stack them (use requestAnimationFrame to ensure height is calculated)
    requestAnimationFrame(() => {
        updateToastPositions();
    });

    // Auto-hide after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('toast-hiding');
            setTimeout(() => {
                toast.remove();
                updateToastPositions();
            }, 300);
        }
    }, 4000);
}

/**
 * Update positions of all toasts to stack them from bottom
 */
function updateToastPositions() {
    const toasts = Array.from(document.querySelectorAll('.toast:not(.toast-hiding)'));
    const baseBottom = 20;
    const spacing = 10;
    
    toasts.forEach((toast, index) => {
        const bottom = baseBottom + (toasts.length - 1 - index) * (toast.offsetHeight + spacing);
        toast.style.bottom = `${bottom}px`;
    });
}

// Link generators translated from utils.py
const linkGenerators = {
    "arxiv": {
        "abstract": "https://arxiv.org/abs/{}",
        "pdf": "https://arxiv.org/pdf/{}.pdf",
    },
    "pubmed": {
        "abstract": "https://pubmed.ncbi.nlm.nih.gov/{}",
    },
    "pmc": {
        "abstract": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{}",
    },
    "doi": {
        "abstract": "https://doi.org/{}",
    },
    "openreview": {
        "abstract": "https://openreview.net/forum?id={}",
        "pdf": "https://openreview.net/pdf?id={}",
    },
    "mlr": {
        "abstract": "https://proceedings.mlr.press/v{}.html",
        "pdf": (lnk) => {
            const parts = lnk.split('/');
            const lastPart = parts[parts.length - 1];
            return `https://proceedings.mlr.press/v${lnk}/${lastPart}.pdf`;
        },
    },
    "dblp": {
        "abstract": "https://dblp.uni-trier.de/rec/{}"
    },
    "semantic_scholar": {
        "abstract": "https://www.semanticscholar.org/paper/{}"
    },
    "openalex": {
        "abstract": "https://openalex.org/{}",
    },
    "orcid": {
        "abstract": "https://orcid.org/{}"
    },
};

/**
 * Parse an exclusion string (format: "type:link") and generate a URL if possible.
 * Returns an object with { type, link, url, kind } or null if no URL can be generated.
 */
function parseExclusion(exclusion) {
    const colonIndex = exclusion.indexOf(':');
    if (colonIndex === -1) {
        return { type: null, link: exclusion, url: null, kind: null };
    }
    
    const type = exclusion.substring(0, colonIndex);
    const link = exclusion.substring(colonIndex + 1);
    
    if (!linkGenerators[type]) {
        return { type, link, url: null, kind: null };
    }
    
    // Try to get abstract URL first, then PDF
    const generators = linkGenerators[type];
    let url = null;
    let kind = null;
    
    if (generators.abstract) {
        if (typeof generators.abstract === 'function') {
            url = generators.abstract(link);
        } else {
            // Replace all occurrences of {} with the link
            url = generators.abstract.replace(/{}/g, link);
        }
        kind = 'abstract';
    } else if (generators.pdf) {
        if (typeof generators.pdf === 'function') {
            url = generators.pdf(link);
        } else {
            // Replace all occurrences of {} with the link
            url = generators.pdf.replace(/{}/g, link);
        }
        kind = 'pdf';
    }
    
    return { type, link, url, kind };
}

function setResults(...elements) {
    const container = document.getElementById('exclusionsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

function setPagination(...elements) {
    const container = document.getElementById('paginationContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

async function fetchExclusions(offset = 0, limit = 100) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        limit: limit.toString(),
    });

    const url = `/api/v1/exclusions?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

async function addExclusions(exclusions) {
    const response = await fetch('/api/v1/exclusions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ exclusions }),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

async function removeExclusions(exclusions) {
    const response = await fetch('/api/v1/exclusions', {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ exclusions }),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function createExclusionElement(exclusion, index) {
    const parsed = parseExclusion(exclusion);
    
    let exclusionDisplay;
    if (parsed.url) {
        // Create a clickable link
        exclusionDisplay = html`
            <a href="${parsed.url}" target="_blank" rel="noopener noreferrer" class="exclusion-link">
                <span class="exclusion-type">${parsed.type}:</span>
                <span class="exclusion-link-text">${parsed.link}</span>
            </a>
        `;
    } else {
        // Display as plain text if no URL can be generated
        exclusionDisplay = html`
            <span class="exclusion-text">${exclusion}</span>
        `;
    }
    
    const exclusionItem = html`
        <div class="exclusion-item" data-exclusion="${exclusion}">
            ${exclusionDisplay}
            <button class="btn btn-danger btn-small remove-exclusion-btn" data-exclusion="${exclusion}">
                Remove
            </button>
        </div>
    `;

    const removeBtn = exclusionItem.querySelector('.remove-exclusion-btn');
    removeBtn.addEventListener('click', async () => {
        try {
            await removeExclusions([exclusion]);
            showToast('Exclusion removed successfully', 'success');
            // Reload the current page
            await displayExclusions(currentOffset, currentLimit);
        } catch (error) {
            showToast(`Failed to remove exclusion: ${error.message}`, 'error');
        }
    });

    return exclusionItem;
}

function createPaginationControls(data, offset, limit) {
    const total = data.total;
    const count = data.count;
    const nextOffset = data.next_offset;
    const currentPage = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);

    const controls = [];

    // Previous button
    const prevDisabled = offset === 0;
    const prevBtn = html`
        <button class="btn btn-secondary pagination-btn" disabled="${prevDisabled}" data-offset="${Math.max(0, offset - limit)}">
            Previous
        </button>
    `;
    if (!prevDisabled) {
        prevBtn.addEventListener('click', () => {
            displayExclusions(Math.max(0, offset - limit), limit);
        });
    }
    controls.push(prevBtn);

    // Page info
    const pageInfo = html`
        <span class="pagination-info">
            Page ${currentPage} of ${totalPages} (${total} total)
        </span>
    `;
    controls.push(pageInfo);

    // Next button
    const nextDisabled = nextOffset === null;
    const nextBtn = html`
        <button class="btn btn-secondary pagination-btn" disabled="${nextDisabled}" data-offset="${nextOffset || offset}">
            Next
        </button>
    `;
    if (!nextDisabled) {
        nextBtn.addEventListener('click', () => {
            displayExclusions(nextOffset, limit);
        });
    }
    controls.push(nextBtn);

    return html`
        <div class="pagination-controls">
            ${controls}
        </div>
    `;
}

function renderExclusions(data, offset, limit) {
    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                No exclusions found.
            </div>
        `;
        setResults(noResults);
        setPagination();
        return;
    }

    const exclusionElements = data.results.map((exclusion, index) => 
        createExclusionElement(exclusion, index)
    );
    const exclusionList = html`<div class="exclusion-list">${exclusionElements}</div>`;

    setResults(exclusionList);

    const pagination = createPaginationControls(data, offset, limit);
    setPagination(pagination);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
    setPagination();
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading exclusions: ${error.message}</div>`);
    setPagination();
}

let currentOffset = 0;
const currentLimit = 100;

export async function displayExclusions(offset = 0, limit = 100) {
    currentOffset = offset;
    displayLoading();

    try {
        const data = await fetchExclusions(offset, limit);
        renderExclusions(data, offset, limit);
    } catch (error) {
        console.error('Failed to load exclusions:', error);
        displayError(error);
    }
}

// Set up add exclusion button
document.addEventListener('DOMContentLoaded', () => {
    const addBtn = document.getElementById('addExclusionBtn');
    const newExclusionInput = document.getElementById('newExclusionInput');
    const bulkAddBtn = document.getElementById('bulkAddExclusionsBtn');
    const bulkExclusionsInput = document.getElementById('bulkExclusionsInput');

    if (addBtn && newExclusionInput) {
        const handleAdd = async () => {
            const exclusion = newExclusionInput.value.trim();
            if (!exclusion) {
                showToast('Please enter an exclusion', 'error');
                return;
            }

            try {
                await addExclusions([exclusion]);
                newExclusionInput.value = '';
                showToast('Exclusion added successfully', 'success');
                // Reload the current page
                await displayExclusions(currentOffset, currentLimit);
            } catch (error) {
                showToast(`Failed to add exclusion: ${error.message}`, 'error');
            }
        };

        addBtn.addEventListener('click', handleAdd);
        newExclusionInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleAdd();
            }
        });
    }

    if (bulkAddBtn && bulkExclusionsInput) {
        bulkAddBtn.addEventListener('click', async () => {
            const text = bulkExclusionsInput.value.trim();
            if (!text) {
                showToast('Please enter exclusions', 'error');
                return;
            }

            const exclusions = text.split('\n')
                .map(line => line.trim())
                .filter(line => line.length > 0);

            if (exclusions.length === 0) {
                showToast('Please enter at least one exclusion', 'error');
                return;
            }

            try {
                const result = await addExclusions(exclusions);
                bulkExclusionsInput.value = '';
                showToast(`Added ${result.added} exclusion(s)`, 'success');
                // Reload the current page
                await displayExclusions(currentOffset, currentLimit);
            } catch (error) {
                showToast(`Failed to add exclusions: ${error.message}`, 'error');
            }
        });
    }
});

