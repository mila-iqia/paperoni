import { html } from './common.js';

/**
 * Generic badge management system for topics, flags, etc.
 */
function renderBadgeField(container, items, config) {
    container.innerHTML = '';

    const wrapper = html`
        <div class="array-field">
            <div class="${config.badgesClass}" id="${config.badgesId}"></div>
            <div class="input-container">
                <input type="text"
                       id="${config.inputId}"
                       placeholder="${config.placeholder}"
                       class="edit-input-large">
            </div>
        </div>
    `;

    const badgesContainer = wrapper.querySelector(`#${config.badgesId}`);
    const newInput = wrapper.querySelector(`#${config.inputId}`);

    // Render existing items as badges
    function renderBadges() {
        badgesContainer.innerHTML = '';
        items.forEach((item, index) => {
            const badge = createBadge(item, index, items, renderBadges, config);
            badgesContainer.appendChild(badge);
        });
    }

    renderBadges();

    // Handle adding new items
    newInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const value = newInput.value.trim();
            if (value) {
                const newItem = config.createItem(value);
                items.push(newItem);
                newInput.value = '';
                renderBadges();
            }
        }
    });

    container.appendChild(wrapper);
}

function createBadge(item, index, items, renderBadges, config) {
    const displayValue = config.getDisplayValue(item);
    const inputValue = config.getInputValue(item, index);
    
    const badge = html`
        <div class="${config.badgeClass}">
            <span>${displayValue}</span>
            <button type="button" class="btn-badge-remove" tabindex="-1">×</button>
            <input type="hidden" name="${inputValue.name}" value="${inputValue.value}">
        </div>
    `;

    badge.querySelector('.btn-badge-remove').addEventListener('click', () => {
        // Remove from the items array
        items.splice(index, 1);
        // Re-render all badges to update indices
        renderBadges();
    });

    return badge;
}

/**
 * Show a toast notification
 */
function showToast(message, type = 'success') {
    // Remove any existing toast
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = html`
        <div class="toast toast-${type}">
            <span class="toast-message">${message}</span>
            <button class="toast-close" type="button">×</button>
        </div>
    `;

    // Add close functionality
    toast.querySelector('.toast-close').addEventListener('click', () => {
        toast.classList.add('toast-hiding');
        setTimeout(() => toast.remove(), 300);
    });

    // Add to page
    document.body.appendChild(toast);

    // Auto-hide after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('toast-hiding');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}

/**
 * Main function to set up the paper edit page
 */
export function editPaper(paperId) {
    const messageContainer = document.getElementById('messageContainer');
    const formContainer = document.getElementById('formContainer');

    // Show loading state
    formContainer.innerHTML = '';
    formContainer.appendChild(html`<div class="loading">Loading paper...</div>`);

    // Fetch the paper data
    fetchPaper(paperId)
        .then((paper) => {
            formContainer.innerHTML = '';
            const form = renderEditForm(paper);
            formContainer.appendChild(form);
        })
        .catch((error) => {
            formContainer.innerHTML = '';
            showError(messageContainer, `Failed to load paper: ${error.message}`);
        });
}

/**
 * Fetch paper data from the API
 */
async function fetchPaper(paperId) {
    const response = await fetch(`/api/v1/paper/${paperId}`, {
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Submit updated paper data to the API
 */
async function submitPaper(paper) {
    const response = await fetch('/api/v1/include', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ papers: [paper] }),
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Show error message
 */
function showError(container, message) {
    container.innerHTML = '';
    container.appendChild(
        html`<div class="error-message">${message}</div>`
    );
}

/**
 * Show success message
 */
function showSuccess(container, message) {
    container.innerHTML = '';
    container.appendChild(
        html`<div class="success-message">${message}</div>`
    );
}

/**
 * Render the edit form for a paper
 */
function renderEditForm(paper) {
    const form = html`
        <form class="edit-form" id="editForm">
            <!-- Basic Information -->
            <div class="form-section">
                <div class="section-header">
                    <h2>Basic Information</h2>
                </div>

                <div class="form-group">
                    <label for="title">Title *</label>
                    <input type="text" id="title" name="title" value="${paper.title || ''}" required>
                </div>

                <div class="form-group">
                    <label for="abstract">Abstract</label>
                    <div id="abstract" 
                         class="editable-abstract" 
                         contenteditable="true" 
                         data-placeholder="Enter the paper abstract..."
                         role="textbox"
                         aria-label="Abstract">${paper.abstract || ''}</div>
                </div>
            </div>

            <!-- Authors -->
            <div class="form-section">
                <h2>Authors</h2>
                <div id="authorsContainer"></div>
            </div>

            <!-- Releases -->
            <div class="form-section">
                <h2>Releases</h2>
                <div id="releasesContainer"></div>
            </div>

            <!-- Topics -->
            <div class="form-section">
                <h2>Topics</h2>
                <div id="topicsContainer"></div>
            </div>

            <!-- Links -->
            <div class="form-section">
                <h2>Links</h2>
                <div id="linksContainer"></div>
            </div>

            <!-- Flags -->
            <div class="form-section">
                <h2>Flags</h2>
                <div id="flagsContainer"></div>
            </div>

            <!-- Form Actions -->
            <div class="form-actions sticky-bottom">
                <button type="submit" class="btn-primary btn-save-sticky">Save Changes</button>
            </div>
        </form>
    `;

    // Populate array fields
    const authorsContainer = form.querySelector('#authorsContainer');
    renderAuthors(authorsContainer, paper.authors || []);

    const releasesContainer = form.querySelector('#releasesContainer');
    renderReleases(releasesContainer, paper.releases || []);

    const topicsContainer = form.querySelector('#topicsContainer');
    renderTopics(topicsContainer, paper.topics || []);

    const linksContainer = form.querySelector('#linksContainer');
    renderLinks(linksContainer, paper.links || []);

    const flagsContainer = form.querySelector('#flagsContainer');
    renderFlags(flagsContainer, Array.from(paper.flags || []));

    // Set up form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const messageContainer = document.getElementById('messageContainer');
        const submitBtn = form.querySelector('button[type="submit"]');

        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        try {
            const updatedPaper = collectFormData(form, paper);
            const result = await submitPaper(updatedPaper);

            if (result.success) {
                showToast('Paper updated successfully!', 'success');
            } else {
                showToast(result.message || 'Failed to update paper', 'error');
            }
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Changes';
        }
    });


    return form;
}

/**
 * Render authors array field
 */
function renderAuthors(container, authors) {
    container.innerHTML = '';

    const tableWrapper = html`
        <div class="array-field">
            <table class="authors-table edit-table">
                <thead>
                    <tr>
                        <th></th>
                        <th>Name</th>
                        <th>Affiliations</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="authorsTableBody"></tbody>
            </table>
        </div>
    `;

    const tbody = tableWrapper.querySelector('#authorsTableBody');

    authors.forEach((author, index) => {
        const row = createAuthorRow(author, index);
        tbody.appendChild(row);
    });

    // Initialize button states
    updateRowIndices(tbody);

    const addBtn = html`<button type="button" class="btn-add input-container">+ Add Author</button>`;
    addBtn.addEventListener('click', () => {
        const newAuthor = {
            display_name: '',
            author: { name: '', aliases: [], links: [] },
            affiliations: []
        };
        const row = createAuthorRow(newAuthor, tbody.children.length);
        tbody.appendChild(row);
        authors.push(newAuthor);
        updateRowIndices(tbody);
        
        // Focus on the name field of the newly added row
        const nameInput = row.querySelector('input[name$=".display_name"]');
        if (nameInput) {
            nameInput.focus();
        }
    });

    tableWrapper.appendChild(addBtn);
    container.appendChild(tableWrapper);
}

function createAuthorRow(author, index) {
    const row = html`
        <tr>
            <td class="cell-center-padded">
                <div class="drag-handle" title="Drag to reorder">⋮⋮</div>
            </td>
            <td>
                <input type="text"
                       name="authors[${index}].display_name"
                       value="${author.display_name || ''}"
                       placeholder="Enter author's name"
                       required
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="authors[${index}].affiliations"
                       value="${(author.affiliations || []).map(a => a.name).join('; ')}"
                       placeholder="Enter affiliations, semicolon-separated"
                       class="edit-input">
            </td>
            <td class="cell-center">
                <button type="button" class="btn-remove-x" tabindex="-1">×</button>
            </td>
        </tr>
    `;

    // Make only the drag handle draggable
    const dragHandle = row.querySelector('.drag-handle');
    dragHandle.draggable = true;
    
    // Add drag event listeners to the handle
    dragHandle.addEventListener('dragstart', handleDragStart);
    
    // Add drop-related event listeners to the row
    row.addEventListener('dragover', handleDragOver);
    row.addEventListener('dragenter', handleDragEnter);
    row.addEventListener('dragleave', handleDragLeave);
    row.addEventListener('drop', handleDrop);
    row.addEventListener('dragend', handleDragEnd);

    row.querySelector('.btn-remove-x').addEventListener('click', () => {
        row.remove();
        updateRowIndices(row.parentNode);
    });

    return row;
}

function updateRowIndices(tbody) {
    // Update the name attributes of all inputs to reflect new positions
    Array.from(tbody.querySelectorAll('tr')).forEach((row, newIndex) => {
        const displayNameInput = row.querySelector('input[name^="authors["]');
        const affiliationsInput = row.querySelectorAll('input[name^="authors["]')[1];

        if (displayNameInput) {
            displayNameInput.name = `authors[${newIndex}].display_name`;
        }
        if (affiliationsInput) {
            affiliationsInput.name = `authors[${newIndex}].affiliations`;
        }
    });
}

// Drag and drop variables
let draggedRow = null;
let draggedIndex = -1;

// Drag and drop handlers
function handleDragStart(e) {
    // 'this' is the drag handle, so we need to get the row (tr element)
    draggedRow = this.closest('tr');
    draggedIndex = Array.from(draggedRow.parentNode.children).indexOf(draggedRow);
    draggedRow.classList.add('dragging');
    
    // Set drag effect
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', draggedRow.outerHTML);
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    
    // Clear all existing drag-over classes
    const tbody = this.parentNode;
    Array.from(tbody.children).forEach(row => {
        row.classList.remove('drag-over', 'drag-over-bottom');
    });
    
    if (this !== draggedRow) {
        // Get mouse position relative to the row
        const rect = this.getBoundingClientRect();
        const mouseY = e.clientY;
        const rowMiddle = rect.top + rect.height / 2;
        
        // Check if this is the last row and we're in the bottom half
        const isLastRow = this === tbody.lastElementChild;
        const isBottomHalf = mouseY > rowMiddle;
        
        if (isLastRow && isBottomHalf) {
            // Show indicator below the last row
            this.classList.add('drag-over-bottom');
        } else {
            // Show indicator above the current row
            this.classList.add('drag-over');
        }
    }
    
    return false;
}

function handleDragEnter(e) {
    // Handled in dragover for better consistency
}

function handleDragLeave(e) {
    // Only remove if we're leaving the row entirely (not just moving to a child element)
    const rect = this.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
        this.classList.remove('drag-over');
    }
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    if (this !== draggedRow) {
        const tbody = this.parentNode;
        
        // Check if we're dropping after the last row
        if (this.classList.contains('drag-over-bottom')) {
            // Insert after this row (at the end)
            tbody.insertBefore(draggedRow, this.nextSibling);
        } else {
            // Insert before this row (normal case)
            tbody.insertBefore(draggedRow, this);
        }
        
        // Update form field indices
        updateRowIndices(tbody);
    }
    
    return false;
}

function handleDragEnd(e) {
    // Clean up - draggedRow is set globally
    if (draggedRow) {
        draggedRow.classList.remove('dragging');
        
        // Remove drag-over classes from all rows
        const tbody = draggedRow.parentNode;
        Array.from(tbody.children).forEach(row => {
            row.classList.remove('drag-over', 'drag-over-bottom');
        });
    }
    
    draggedRow = null;
    draggedIndex = -1;
}

/**
 * Render releases array field
 */
function renderReleases(container, releases) {
    container.innerHTML = '';

    const tableWrapper = html`
        <div class="array-field">
            <table class="releases-table edit-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Venue Name</th>
                        <th>Type</th>
                        <th>Series</th>
                        <th>Status</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="releasesTableBody"></tbody>
            </table>
        </div>
    `;

    const tbody = tableWrapper.querySelector('#releasesTableBody');

    releases.forEach((release, index) => {
        const row = createReleaseRow(release, index);
        tbody.appendChild(row);
    });

    const addBtn = html`<button type="button" class="btn-add input-container">+ Add Release</button>`;
    addBtn.addEventListener('click', () => {
        const newRelease = {
            venue: {
                type: 'conference',
                name: '',
                series: '',
                date: new Date().toISOString().split('T')[0],
                date_precision: 3
            },
            status: 'published'
        };
        const row = createReleaseRow(newRelease, tbody.children.length);
        tbody.appendChild(row);
        releases.push(newRelease);
        
        // Focus on the date field of the newly added row
        const dateInput = row.querySelector('input[type="date"]');
        if (dateInput) {
            dateInput.focus();
        }
    });

    tableWrapper.appendChild(addBtn);
    container.appendChild(tableWrapper);
}

function createReleaseRow(release, index) {
    const row = html`
        <tr>
            <td>
                <input type="date"
                       name="releases[${index}].venue.date"
                       value="${release.venue?.date || ''}"
                       required
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="releases[${index}].venue.name"
                       value="${release.venue?.name || ''}"
                       required
                       class="edit-input">
            </td>
            <td>
                <select name="releases[${index}].venue.type" required
                        class="edit-input">
                    <option value="conference" selected="${release.venue?.type === 'conference'}">Conference</option>
                    <option value="journal" selected="${release.venue?.type === 'journal'}">Journal</option>
                    <option value="workshop" selected="${release.venue?.type === 'workshop'}">Workshop</option>
                    <option value="preprint" selected="${release.venue?.type === 'preprint'}">Preprint</option>
                </select>
            </td>
            <td>
                <input type="text"
                       name="releases[${index}].venue.series"
                       value="${release.venue?.series || ''}"
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="releases[${index}].status"
                       value="${release.status || 'published'}"
                       required
                       class="edit-input">
            </td>
            <td class="cell-center">
                <button type="button" class="btn-remove-x" tabindex="-1">×</button>
            </td>
        </tr>
    `;

    row.querySelector('.btn-remove-x').addEventListener('click', () => {
        row.remove();
    });

    return row;
}

/**
 * Render topics array field
 */
function renderTopics(container, topics) {
    const config = {
        badgesClass: 'topics-badges',
        badgesId: 'topicsBadges',
        inputId: 'newTopicInput',
        placeholder: 'Type a topic and press Enter to add...',
        badgeClass: 'topic-badge',
        createItem: (value) => ({ name: value }),
        getDisplayValue: (item) => item.name || '',
        getInputValue: (item, index) => ({
            name: `topics[${index}].name`,
            value: item.name || ''
        })
    };
    
    renderBadgeField(container, topics, config);
}


/**
 * Render links array field
 */
function renderLinks(container, links) {
    container.innerHTML = '';

    const tableWrapper = html`
        <div class="array-field">
            <table class="links-table edit-table">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Link</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="linksTableBody"></tbody>
            </table>
        </div>
    `;

    const tbody = tableWrapper.querySelector('#linksTableBody');

    // Sort links by type (case-insensitive), with empty types at the end
    const sortedLinks = [...links].sort((a, b) => {
        const typeA = (a.type || '').toLowerCase();
        const typeB = (b.type || '').toLowerCase();
        
        // Empty types go to the end
        if (!typeA && !typeB) return 0;
        if (!typeA) return 1;
        if (!typeB) return -1;
        
        return typeA.localeCompare(typeB);
    });

    sortedLinks.forEach((link, index) => {
        const row = createLinkRow(link, index);
        tbody.appendChild(row);
    });

    const addBtn = html`<button type="button" class="btn-add input-container">+ Add Link</button>`;
    addBtn.addEventListener('click', () => {
        const newLink = {
            type: '',
            link: ''
        };
        const row = createLinkRow(newLink, tbody.children.length);
        tbody.appendChild(row);
        links.push(newLink);
    });

    tableWrapper.appendChild(addBtn);
    container.appendChild(tableWrapper);
}

function createLinkRow(link, index) {
    const row = html`
        <tr>
            <td>
                <input type="text"
                       name="links[${index}].type"
                       value="${link.type || ''}"
                       placeholder="e.g., doi, url, arxiv, pdf"
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="links[${index}].link"
                       value="${link.link || ''}"
                       placeholder="Enter the link or identifier"
                       class="edit-input">
            </td>
            <td class="cell-center">
                <button type="button" class="btn-remove-x" tabindex="-1">×</button>
            </td>
        </tr>
    `;

    row.querySelector('.btn-remove-x').addEventListener('click', () => {
        row.remove();
    });

    return row;
}

/**
 * Render flags array field
 */
function renderFlags(container, flags) {
    const config = {
        badgesClass: 'flags-badges',
        badgesId: 'flagsBadges',
        inputId: 'newFlagInput',
        placeholder: 'Type a flag name and press Enter to add...',
        badgeClass: 'flag-badge',
        createItem: (value) => value,
        getDisplayValue: (item) => item || '',
        getInputValue: (item, index) => ({
            name: `flags[${index}]`,
            value: item || ''
        })
    };
    
    renderBadgeField(container, flags, config);
}


/**
 * Collect form data and build updated paper object
 */
function collectFormData(form, originalPaper) {
    const formData = new FormData(form);

    // Start with the original paper to preserve fields like id, version
    const paper = {
        ...originalPaper,
        title: formData.get('title'),
        abstract: form.querySelector('#abstract').textContent.trim() || null,
        authors: [],
        releases: [],
        topics: [],
        links: [],
        flags: []
    };

    // Collect authors
    const authorElements = form.querySelectorAll('[name^="authors["]');
    const authorsMap = {};

    authorElements.forEach(input => {
        const match = input.name.match(/authors\[(\d+)\]\.(.+)/);
        if (match) {
            const [, index, field] = match;
            if (!authorsMap[index]) {
                authorsMap[index] = {
                    display_name: '',
                    author: { name: '', aliases: [], links: [] },
                    affiliations: []
                };
            }

            if (field === 'display_name') {
                authorsMap[index].display_name = input.value;
                // Automatically copy display_name to author.name
                authorsMap[index].author.name = input.value;
            } else if (field === 'affiliations') {
                authorsMap[index].affiliations = input.value
                    .split(';')
                    .map(s => s.trim())
                    .filter(s => s)
                    .map(name => ({ name, category: 'unknown', country: null, aliases: [] }));
            }
        }
    });
    paper.authors = Object.values(authorsMap);

    // Collect releases
    const releaseElements = form.querySelectorAll('[name^="releases["]');
    const releasesMap = {};

    releaseElements.forEach(input => {
        const match = input.name.match(/releases\[(\d+)\]\.(.+)/);
        if (match) {
            const [, index, field] = match;
            if (!releasesMap[index]) {
                releasesMap[index] = {
                    venue: {
                        type: 'conference',
                        name: '',
                        series: '',
                        date: '',
                        date_precision: 3,
                        volume: null,
                        publisher: null,
                        short_name: null,
                        aliases: [],
                        links: [],
                        open: false,
                        peer_reviewed: false
                    },
                    status: 'published',
                    pages: null
                };
            }

            const parts = field.split('.');
            if (parts.length === 1) {
                releasesMap[index][parts[0]] = input.value;
            } else if (parts[0] === 'venue') {
                releasesMap[index].venue[parts[1]] = input.value;
            }
        }
    });
    paper.releases = Object.values(releasesMap);

    // Collect topics
    const topicElements = form.querySelectorAll('[name^="topics["]');
    const topicsMap = {};

    topicElements.forEach(input => {
        const match = input.name.match(/topics\[(\d+)\]\.name/);
        if (match) {
            const [, index] = match;
            topicsMap[index] = { name: input.value };
        }
    });
    paper.topics = Object.values(topicsMap);

    // Collect links
    const linkElements = form.querySelectorAll('[name^="links["]');
    const linksMap = {};

    linkElements.forEach(input => {
        const match = input.name.match(/links\[(\d+)\]\.(.+)/);
        if (match) {
            const [, index, field] = match;
            if (!linksMap[index]) {
                linksMap[index] = { type: '', link: '' };
            }
            linksMap[index][field] = input.value;
        }
    });
    
    // Sort links by type (case-insensitive), with empty types at the end
    const collectedLinks = Object.values(linksMap);
    paper.links = collectedLinks.sort((a, b) => {
        const typeA = (a.type || '').toLowerCase();
        const typeB = (b.type || '').toLowerCase();
        
        // Empty types go to the end
        if (!typeA && !typeB) return 0;
        if (!typeA) return 1;
        if (!typeB) return -1;
        
        return typeA.localeCompare(typeB);
    });

    // Collect flags
    const flagElements = form.querySelectorAll('[name^="flags["]');
    const flagsArray = [];

    flagElements.forEach(input => {
        if (input.value.trim()) {
            flagsArray.push(input.value.trim());
        }
    });
    paper.flags = flagsArray;

    return paper;
}
