import { html } from './common.js';

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
    const exclusionItem = html`
        <div class="exclusion-item" data-exclusion="${exclusion}">
            <span class="exclusion-text">${exclusion}</span>
            <button class="btn btn-danger btn-small remove-exclusion-btn" data-exclusion="${exclusion}">
                Remove
            </button>
        </div>
    `;

    const removeBtn = exclusionItem.querySelector('.remove-exclusion-btn');
    removeBtn.addEventListener('click', async () => {
        try {
            await removeExclusions([exclusion]);
            // Reload the current page
            await displayExclusions(currentOffset, currentLimit);
        } catch (error) {
            alert(`Failed to remove exclusion: ${error.message}`);
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
                alert('Please enter an exclusion');
                return;
            }

            try {
                await addExclusions([exclusion]);
                newExclusionInput.value = '';
                // Reload the current page
                await displayExclusions(currentOffset, currentLimit);
            } catch (error) {
                alert(`Failed to add exclusion: ${error.message}`);
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
                alert('Please enter exclusions');
                return;
            }

            const exclusions = text.split('\n')
                .map(line => line.trim())
                .filter(line => line.length > 0);

            if (exclusions.length === 0) {
                alert('Please enter at least one exclusion');
                return;
            }

            try {
                const result = await addExclusions(exclusions);
                bulkExclusionsInput.value = '';
                alert(`Added ${result.added} exclusion(s)`);
                // Reload the current page
                await displayExclusions(currentOffset, currentLimit);
            } catch (error) {
                alert(`Failed to add exclusions: ${error.message}`);
            }
        });
    }
});

