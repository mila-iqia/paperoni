import { escapeHtml, html, showToast } from './common.js';
import { getTranslation, setLanguageNode } from './translate.js';

/**
 * Generic badge management system for topics, flags, etc.
 */
function renderBadgeField(container, items, config) {
    container.innerHTML = '';

    const placeholder = config.placeholderKey ? getTranslation(config.placeholderKey) : (config.placeholder || '');
    const wrapper = html`
        <div class="array-field">
            <div class="${config.badgesClass}" id="${config.badgesId}"></div>
            <div class="input-container">
                <input type="text"
                       id="${config.inputId}"
                       placeholder="${placeholder}"
                       data-loc-placeholder="${config.placeholderKey || ''}"
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
 * Main function to set up the paper edit page.
 * suggestMode: when true, submit to /suggest (pending validation); when false, submit to /include (direct edit).
 */
export function editPaper(paperId, suggestMode = false) {
    const messageContainer = document.getElementById('messageContainer');
    const formContainer = document.getElementById('formContainer');

    // Check if creating a new paper
    if (paperId === 'new') {
        const pageTitle = getTranslation(suggestMode ? 'Suggest New Paper' : 'Create Paper');
        document.title = pageTitle;
        const h1 = document.querySelector('h1');
        if (h1) h1.textContent = pageTitle;

        formContainer.innerHTML = '';
        const paper = {
            id: null,
            title: '',
            abstract: '',
            authors: [],
            releases: [],
            topics: [],
            links: [],
            flags: []
        };
        const form = renderEditForm(paper, suggestMode);
        formContainer.appendChild(form);
        setLanguageNode(formContainer);
        return;
    }

    // Show loading state
    formContainer.innerHTML = '';
    formContainer.appendChild(html`<div class="loading"><loc>Loading paper...</loc></div>`);
    setLanguageNode(formContainer);

    // Fetch the paper data
    fetchPaper(paperId)
        .then((paper) => {
            const pageTitle = getTranslation(suggestMode ? 'Suggest Edit' : 'Edit Paper');
            document.title = pageTitle;
            const h1 = document.querySelector('h1');
            if (h1) h1.textContent = pageTitle;

            formContainer.innerHTML = '';
            const form = renderEditForm(paper, suggestMode);
            formContainer.appendChild(form);
            setLanguageNode(formContainer);
        })
        .catch((error) => {
            formContainer.innerHTML = '';
            showError(messageContainer, getTranslation('Failed to load paper: {1}').replace('{1}', error.message));
        });
}

/**
 * Fetch paper data from the API
 * Passes latest_edit=true as a query parameter.
 */
async function fetchPaper(paperId) {
    const response = await fetch(`/api/v1/paper/${paperId}?latest_edit=true`, {
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Submit updated paper data to the API.
 * suggestMode: use /suggest (pending) or /include (direct).
 */
async function submitPaper(paper, comment = '', suggestMode = false) {
    const endpoint = suggestMode ? '/api/v1/suggest' : '/api/v1/include';
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ papers: [paper], comment: comment || '' }),
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Delete a paper via the /delete API (direct mode only).
 */
async function deletePaper(paperId) {
    const response = await fetch('/api/v1/delete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ ids: [String(paperId)] }),
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
        html`<div class="error-message">${escapeHtml(message)}</div>`
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

function getSubmitButtonText(paper, suggestMode, deleteMode = false) {
    if (deleteMode && paper.id) {
        return suggestMode ? 'Mark for deletion' : 'Delete';
    }
    if (suggestMode) {
        return paper.id ? 'Submit Suggestion' : 'Suggest Paper';
    }
    return paper.id ? 'Save Changes' : 'Create Paper';
}

/**
 * Render the edit form for a paper.
 * suggestMode: when true, wording reflects suggest/pending flow.
 */
function renderEditForm(paper, suggestMode = false) {
    const editPending = paper.info?.edit_pending === true;
    if (editPending) {
        delete paper.info.edit_pending;
    }

    const editPendingNote = editPending
        ? html`<span class="edit-pending-note"><loc>(based on existing pending edit)</loc></span>`
        : null;

    const form = html`
        <form class="edit-form" id="editForm">
            <!-- Basic Information -->
            <div class="form-section">
                <div class="section-header">
                    <h2><loc>Basic Information</loc> ${editPendingNote}</h2>
                    ${paper.id ? html`<button type="button" class="btn-delete-toggle" id="deleteToggleBtn"><loc>${suggestMode ? 'Mark for deletion' : 'Delete'}</loc></button>` : null}
                </div>

                <div class="form-group">
                    <label for="title"><loc>Title *</loc></label>
                    <input type="text" id="title" name="title" value="${paper.title || ''}" required>
                </div>

                <div class="form-group">
                    <label for="abstract"><loc>Abstract</loc></label>
                    <div id="abstract"
                         class="editable-abstract"
                         contenteditable="true"
                         data-placeholder="Enter the paper abstract..."
                         data-loc-placeholder="Enter the paper abstract..."
                         role="textbox"
                         aria-label="Abstract">${paper.abstract || ''}</div>
                </div>
            </div>

            <!-- Authors -->
            <div class="form-section">
                <h2><loc>Authors</loc></h2>
                <div id="authorsContainer"></div>
            </div>

            <!-- Releases -->
            <div class="form-section">
                <h2><loc>Releases</loc></h2>
                <div id="releasesContainer"></div>
            </div>

            <!-- Topics -->
            <div class="form-section">
                <h2><loc>Topics</loc></h2>
                <div id="topicsContainer"></div>
            </div>

            <!-- Links -->
            <div class="form-section">
                <h2><loc>Links</loc></h2>
                <div id="linksContainer"></div>
            </div>

            <!-- Flags -->
            <div class="form-section">
                <h2><loc>Flags</loc></h2>
                <div id="flagsContainer"></div>
            </div>

            <!-- Metadata -->
            <div class="form-section">
                <div class="section-header">
                    <h2><loc>Metadata</loc></h2>
                </div>

                <div class="form-group">
                    <label for="key"><loc>Key</loc></label>
                    <input type="text" id="key" name="key" value="${paper.key || 'n/a'}" placeholder="Paper key identifier" data-loc-placeholder="Paper key identifier" class="edit-input">
                </div>

                <div class="form-group">
                    <label for="version"><loc>Version</loc></label>
                    <input type="text" id="version" name="version" value="${paper.version ? new Date(paper.version).toLocaleString() : ''}" readonly class="edit-input readonly-input" title="Last modified timestamp (read-only)" data-loc-title="Last modified timestamp (read-only)" placeholder="Not set" data-loc-placeholder="Not set">
                </div>

                <div class="form-group">
                    <label><loc>Info</loc></label>
                    <div id="infoContainer"></div>
                </div>
            </div>

            <!-- Comment -->
            <div class="form-section">
                <div class="form-group">
                    <label for="comment"><loc>Comment</loc></label>
                    <textarea id="comment" name="comment" class="edit-input" rows="3" placeholder="${suggestMode ? 'Comment about this edit, for the person who will validate it' : 'Optional note about this edit'}" data-loc-placeholder="${suggestMode ? 'Comment about this edit, for the person who will validate it' : 'Optional note about this edit'}"></textarea>
                </div>
            </div>

            <!-- Form Actions -->
            <div class="form-actions sticky-bottom">
                <button type="submit" class="btn-primary btn-save-sticky" id="submitBtn"><loc>${getSubmitButtonText(paper, suggestMode)}</loc></button>
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

    const infoContainer = form.querySelector('#infoContainer');
    renderInfo(infoContainer, paper.info || {});

    // Delete toggle: when on, submit button says Delete/Mark for deletion; submit adds mark:delete
    let deleteMode = false;
    const deleteToggleBtn = form.querySelector('#deleteToggleBtn');
    const submitBtn = form.querySelector('#submitBtn');
    if (deleteToggleBtn && submitBtn) {
        deleteToggleBtn.addEventListener('click', () => {
            deleteMode = !deleteMode;
            deleteToggleBtn.classList.toggle('active', deleteMode);
            submitBtn.classList.toggle('btn-save-delete', deleteMode);
            const btnKey = getSubmitButtonText(paper, suggestMode, deleteMode);
            submitBtn.innerHTML = '<loc>' + btnKey + '</loc>';
            setLanguageNode(submitBtn);
            if (deleteMode && suggestMode) {
                form.querySelector('#comment')?.focus();
            }
        });
    }

    // Set up form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const messageContainer = document.getElementById('messageContainer');
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnKey = getSubmitButtonText(paper, suggestMode, deleteMode);

        submitBtn.disabled = true;
        const loadingKey = suggestMode ? 'Submitting...' : (deleteMode ? 'Deleting...' : 'Saving...');
        submitBtn.innerHTML = '<loc>' + loadingKey + '</loc>';
        setLanguageNode(submitBtn);

        try {
            const comment = form.querySelector('#comment')?.value?.trim() || '';

            if (deleteMode && suggestMode) {
                // Suggest mode: submit with mark:delete to /suggest
                let updatedPaper = collectFormData(form, paper);
                updatedPaper = { ...updatedPaper, flags: [...(updatedPaper.flags || []), 'mark:delete'] };
                if (!comment) {
                    showToast(getTranslation('Give a reason for deletion in the comment'), 'error');
                    form.querySelector('#comment')?.focus();
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<loc>' + originalBtnKey + '</loc>';
                    setLanguageNode(submitBtn);
                    return;
                }
                const result = await submitPaper(updatedPaper, comment, true);
                if (result.success) {
                    showToast(getTranslation('Edit suggested! It will appear in the pending queue for validation.'), 'success');
                } else {
                    showToast(result.message || getTranslation('Failed to submit suggestion'), 'error');
                }
            } else if (deleteMode && !suggestMode) {
                const result = await deletePaper(paper.id);
                if (result.success) {
                    showToast(getTranslation('Paper deleted successfully!'), 'success');
                    window.location.href = '/search';
                } else {
                    showToast(result.message || getTranslation('Failed to delete paper'), 'error');
                }
            } else {
                const updatedPaper = collectFormData(form, paper);
                if (!updatedPaper.title || !updatedPaper.title.trim()) {
                    showToast(getTranslation('Title cannot be empty'), 'error');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<loc>' + originalBtnKey + '</loc>';
                    setLanguageNode(submitBtn);
                    return;
                }
                for (const author of updatedPaper.authors) {
                    if (!author.display_name || !author.display_name.trim()) {
                        showToast(getTranslation('Author name cannot be empty'), 'error');
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<loc>' + originalBtnKey + '</loc>';
                        setLanguageNode(submitBtn);
                        return;
                    }
                }
                for (const release of updatedPaper.releases) {
                    if (!release.venue || !release.venue.name || !release.venue.name.trim()) {
                        showToast(getTranslation('Venue name cannot be empty'), 'error');
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<loc>' + originalBtnKey + '</loc>';
                        setLanguageNode(submitBtn);
                        return;
                    }
                }
                if (paper.id && papersEqual(paper, updatedPaper)) {
                    showToast(getTranslation('No changes to save'), 'error');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<loc>' + originalBtnKey + '</loc>';
                    setLanguageNode(submitBtn);
                    return;
                }
                const result = await submitPaper(updatedPaper, comment, suggestMode);
                if (result.success) {
                    const isNew = paper.id === null;
                    if (result.ids && result.ids.length > 0 && isNew) {
                        paper.id = result.ids[0];
                    }
                    const successKey = suggestMode
                        ? (isNew ? 'Suggestion submitted! It will appear in the pending queue for validation.' : 'Edit suggested! It will appear in the pending queue for validation.')
                        : (isNew ? 'Paper created successfully!' : 'Paper updated successfully!');
                    showToast(getTranslation(successKey), 'success');
                    if (isNew) {
                        window.history.replaceState(null, '', `/edit/${paper.id}${suggestMode ? '?suggest=1' : ''}`);
                    }
                    document.title = getTranslation(suggestMode ? 'Suggest Edit' : 'Edit Paper');
                    const h1 = document.querySelector('h1');
                    if (h1) h1.textContent = getTranslation(suggestMode ? 'Suggest Edit' : 'Edit Paper');
                } else {
                    showToast(result.message || getTranslation('Failed to update paper'), 'error');
                }
            }
        } catch (error) {
            showToast(getTranslation('Error: {1}').replace('{1}', error.message), 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<loc>' + getSubmitButtonText(paper, suggestMode, deleteMode) + '</loc>';
            setLanguageNode(submitBtn);
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
                        <th><loc>Name</loc></th>
                        <th><loc>Affiliations</loc></th>
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

    const addBtn = html`<button type="button" class="btn-add input-container"><loc>+ Add Author</loc></button>`;
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
                <div class="drag-handle" title="Drag to reorder" data-loc-title="Drag to reorder">⋮⋮</div>
            </td>
            <td>
                <input type="text"
                       name="authors[${index}].display_name"
                       value="${author.display_name || ''}"
                       placeholder="Enter author's name"
                       data-loc-placeholder="Enter author's name"
                       required
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="authors[${index}].affiliations"
                       value="${(author.affiliations || []).map(a => a.name).join('; ')}"
                       placeholder="Enter affiliations, semicolon-separated"
                       data-loc-placeholder="Enter affiliations, semicolon-separated"
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
                        <th><loc>Date</loc></th>
                        <th><loc>Venue Name</loc></th>
                        <th><loc>Type</loc></th>
                        <th><loc>Peer review</loc></th>
                        <th><loc>Raw status</loc></th>
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

    const addBtn = html`<button type="button" class="btn-add input-container"><loc>+ Add Release</loc></button>`;
    addBtn.addEventListener('click', () => {
        const newRelease = {
            venue: {
                type: 'conference',
                name: '',
                series: '',
                date: new Date().toISOString().split('T')[0],
                date_precision: 3
            },
            status: 'published',
            peer_review_status: 'unknown'
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
                    <option value="conference"><loc>Conference</loc></option>
                    <option value="journal"><loc>Journal</loc></option>
                    <option value="workshop"><loc>Workshop</loc></option>
                    <option value="preprint"><loc>Preprint</loc></option>
                </select>
            </td>
            <td>
                <select name="releases[${index}].peer_review_status" required
                        class="edit-input">
                    <option value="peer-reviewed"><loc>Peer-reviewed</loc></option>
                    <option value="preprint"><loc>Preprint</loc></option>
                    <option value="workshop"><loc>Workshop</loc></option>
                    <option value="other"><loc>Other</loc></option>
                    <option value="unknown"><loc>Unknown</loc></option>
                </select>
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

    // Set select values programmatically (more reliable than selected attribute)
    const typeSelect = row.querySelector(`[name="releases[${index}].venue.type"]`);
    const peerReviewSelect = row.querySelector(`[name="releases[${index}].peer_review_status"]`);
    if (typeSelect) typeSelect.value = release.venue?.type || 'conference';
    if (peerReviewSelect) peerReviewSelect.value = release.peer_review_status || 'unknown';

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
        placeholderKey: 'Type a topic and press Enter to add...',
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
                        <th><loc>Type</loc></th>
                        <th><loc>Link</loc></th>
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

    const addBtn = html`<button type="button" class="btn-add input-container"><loc>+ Add Link</loc></button>`;
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
                       data-loc-placeholder="e.g., doi, url, arxiv, pdf"
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="links[${index}].link"
                       value="${link.link || ''}"
                       placeholder="Enter the link or identifier"
                       data-loc-placeholder="Enter the link or identifier"
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
        placeholderKey: 'Type a flag name and press Enter to add...',
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
 * Render info key-value pairs as a table
 */
function renderInfo(container, info) {
    container.innerHTML = '';

    // Convert info object to array of {key, value} pairs
    const infoItems = Object.entries(info || {}).map(([key, value]) => ({
        key,
        value: typeof value === 'string' ? value : JSON.stringify(value)
    }));

    const tableWrapper = html`
        <div class="array-field">
            <table class="info-table edit-table">
                <thead>
                    <tr>
                        <th><loc>Key</loc></th>
                        <th><loc>Value (JSON or string)</loc></th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="infoTableBody"></tbody>
            </table>
        </div>
    `;

    const tbody = tableWrapper.querySelector('#infoTableBody');

    infoItems.forEach((item, index) => {
        const row = createInfoRow(item, index);
        tbody.appendChild(row);
    });

    const addBtn = html`<button type="button" class="btn-add input-container"><loc>+ Add Info</loc></button>`;
    addBtn.addEventListener('click', () => {
        const newItem = { key: '', value: '' };
        const row = createInfoRow(newItem, tbody.children.length);
        tbody.appendChild(row);
        
        // Focus on the key field of the newly added row
        const keyInput = row.querySelector('input[name$=".key"]');
        if (keyInput) {
            keyInput.focus();
        }
    });

    tableWrapper.appendChild(addBtn);
    container.appendChild(tableWrapper);
}

function createInfoRow(item, index) {
    const row = html`
        <tr>
            <td>
                <input type="text"
                       name="info[${index}].key"
                       value="${item.key || ''}"
                       placeholder="Key name"
                       data-loc-placeholder="Key name"
                       class="edit-input">
            </td>
            <td>
                <input type="text"
                       name="info[${index}].value"
                       value="${item.value || ''}"
                       placeholder="Value (JSON or plain text)"
                       data-loc-placeholder="Value (JSON or plain text)"
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
 * Normalize a paper for comparison (editable fields only).
 * Order of authors, topics, flags is preserved.
 * Links are sorted (collectFormData always sorts them).
 * Dates are normalized to YYYY-MM-DD (form uses date inputs).
 */
function normalizeForComparison(p) {
    const sortedInfo = (info) => {
        if (!info || typeof info !== 'object') return {};
        return Object.fromEntries(
            Object.entries(info)
                .filter(([k]) => k && k.trim())
                .sort(([a], [b]) => a.localeCompare(b))
        );
    };
    const toDateStr = (d) => {
        const s = (d || '').toString().trim();
        const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
        return m ? m[0] : s;
    };
    const sortLinks = (links) =>
        [...(links || [])]
            .map((l) => ({ type: (l.type || '').trim(), link: (l.link || '').trim() }))
            .sort((a, b) => {
                const typeA = (a.type || '').toLowerCase();
                const typeB = (b.type || '').toLowerCase();
                if (!typeA && !typeB) return 0;
                if (!typeA) return 1;
                if (!typeB) return -1;
                return typeA.localeCompare(typeB) || (a.link || '').localeCompare(b.link || '');
            });
    return {
        title: (p.title || '').trim(),
        abstract: (p.abstract || '').trim() || null,
        key: ((p.key || 'n/a') + '').trim(),
        info: sortedInfo(p.info),
        authors: (p.authors || []).map((a) => ({
            display_name: (a.display_name || '').trim(),
            affiliations: (a.affiliations || []).map((x) => (x.name || '').trim()).filter(Boolean).join('; '),
        })),
        releases: (p.releases || []).map((r) => ({
            venue: {
                date: toDateStr(r.venue?.date),
                name: (r.venue?.name || '').trim(),
                type: r.venue?.type || 'conference',
            },
            peer_review_status: r.peer_review_status || 'unknown',
            status: (r.status || 'published').trim(),
        })),
        topics: (p.topics || []).map((t) => (t.name || '').trim()),
        links: sortLinks(p.links),
        flags: (p.flags || []).map((f) => (f + '').trim()),
    };
}

/**
 * True if the two papers have identical editable content.
 */
function papersEqual(a, b) {
    return JSON.stringify(normalizeForComparison(a)) === JSON.stringify(normalizeForComparison(b));
}

/**
 * Collect form data and build updated paper object
 */
function collectFormData(form, originalPaper) {
    const formData = new FormData(form);

    // Start with the original paper to preserve fields like id, version
    // Collect info from table
    const infoElements = form.querySelectorAll('[name^="info["]');
    const infoMap = {};

    infoElements.forEach(input => {
        const match = input.name.match(/info\[(\d+)\]\.(.+)/);
        if (match) {
            const [, index, field] = match;
            if (!infoMap[index]) {
                infoMap[index] = { key: '', value: '' };
            }
            infoMap[index][field] = input.value;
        }
    });

    // Build info object from collected key-value pairs
    const infoValue = {};
    Object.values(infoMap).forEach(item => {
        if (item.key && item.key.trim()) {
            const key = item.key.trim();
            const valueStr = item.value || '';
            // Try to parse as JSON, otherwise use as string
            try {
                infoValue[key] = JSON.parse(valueStr);
            } catch (e) {
                infoValue[key] = valueStr;
            }
        }
    });

    const paper = {
        ...originalPaper,
        title: formData.get('title'),
        abstract: form.querySelector('#abstract').textContent.trim() || null,
        key: formData.get('key') || 'n/a',
        info: infoValue,
        // version is read-only, preserve from originalPaper
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
                const originalAuthor = originalPaper.authors?.[parseInt(index, 10)];
                const originalAffiliations = originalAuthor?.affiliations || [];
                const originalStr = originalAffiliations.map(a => a.name.trim()).filter(Boolean).join('; ');
                const inputStr = input.value.split(';').map(s => s.trim()).filter(Boolean).join('; ');

                if (inputStr === originalStr) {
                    authorsMap[index].affiliations = originalAffiliations.map(a => ({ ...a }));
                } else {
                    authorsMap[index].affiliations = input.value
                        .split(';')
                        .map(s => s.trim())
                        .filter(s => s)
                        .map(name => ({ name, category: 'unknown', country: null, aliases: [] }));
                }
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
                    peer_review_status: 'unknown',
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
