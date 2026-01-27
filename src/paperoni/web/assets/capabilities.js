import { html } from './common.js';

let usersData = {};
let capabilitiesGraph = {};
let allCapabilities = [];
let prefix = '';

// Get capabilities in graph order
function getOrderedCapabilities() {
    return allCapabilities; // Already in graph order from API
}

// Check if a capability is implicit (implied by another capability the user has)
function isImplicitCapability(email, capability) {
    const userCaps = new Set(usersData[email] || []);
    
    // If the user doesn't have this capability directly, it can't be implicit
    if (!userCaps.has(capability)) {
        return false;
    }
    
    // Check if this capability is implied by any of the user's other direct capabilities
    for (const userCap of userCaps) {
        if (userCap === capability) continue; // Skip if it's the same capability
        const implied = getImpliedCapabilities(userCap);
        if (implied.has(capability)) {
            return true;
        }
    }
    return false;
}

function getImpliedCapabilities(capability) {
    const implied = new Set([capability]);
    const queue = [capability];
    
    while (queue.length > 0) {
        const current = queue.shift();
        const implies = capabilitiesGraph[current] || [];
        for (const impliedCap of implies) {
            if (!implied.has(impliedCap)) {
                implied.add(impliedCap);
                queue.push(impliedCap);
            }
        }
    }
    
    return implied;
}

async function fetchCapabilitiesList() {
    try {
        const response = await fetch(`${prefix}/manage_capabilities/list`);
        if (!response.ok) {
            throw new Error(`Failed to fetch capabilities: ${response.statusText}`);
        }
        const data = await response.json();
        usersData = data.users || {};
        capabilitiesGraph = data.graph || {};
        allCapabilities = Object.keys(capabilitiesGraph);
        return data;
    } catch (error) {
        console.error('Error fetching capabilities:', error);
        throw error;
    }
}

async function addCapability(email, capability) {
    try {
        const response = await fetch(`${prefix}/manage_capabilities/add`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, capability }),
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Failed to add capability: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error adding capability:', error);
        throw error;
    }
}

async function removeCapability(email, capability) {
    try {
        const response = await fetch(`${prefix}/manage_capabilities/remove`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, capability }),
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Failed to remove capability: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error removing capability:', error);
        throw error;
    }
}

function createCapabilityBadge(email, capability, isImplicit) {
    const badge = html`
        <span class="topic-badge ${isImplicit ? 'implicit-capability' : ''}">
            ${capability}
            ${!isImplicit ? html`<button type="button" class="btn-badge-remove" data-email="${email}" data-capability="${capability}" tabindex="-1">×</button>` : ''}
        </span>
    `;
    
    // Only add remove functionality for explicit capabilities
    if (!isImplicit) {
        const removeBtn = badge.querySelector('.btn-badge-remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    await removeCapability(email, capability);
                    await fetchCapabilitiesList();
                    renderTable();
                } catch (error) {
                    showError(error.message);
                }
            });
        }
    }
    
    return badge;
}

function createAutocompleteInput(email, existingCapabilities) {
    const container = html`<div class="capability-input-container"></div>`;
    const input = html`<input type="text" class="edit-input capability-autocomplete" placeholder="Type to add capability..." autocomplete="off">`;
    const suggestions = html`<div class="autocomplete-suggestions" style="display: none;"></div>`;
    
    container.appendChild(input);
    container.appendChild(suggestions);
    
    let selectedIndex = -1;
    let currentSuggestions = [];
    
    function filterSuggestions(query) {
        const userCaps = new Set(existingCapabilities || []);
        const queryLower = query.toLowerCase();
        
        // Calculate all capabilities the user already has (explicit + implicit)
        const allUserCapabilities = new Set();
        userCaps.forEach(cap => {
            const implied = getImpliedCapabilities(cap);
            implied.forEach(impliedCap => allUserCapabilities.add(impliedCap));
        });
        
        return getOrderedCapabilities().filter(cap => {
            // Don't show capabilities the user already has (explicit or implicit)
            if (allUserCapabilities.has(cap)) return false;
            // Filter by query
            return cap.toLowerCase().includes(queryLower);
        });
    }
    
    function showSuggestions(query) {
        currentSuggestions = filterSuggestions(query || '');
        selectedIndex = -1;
        
        if (currentSuggestions.length === 0) {
            suggestions.style.display = 'none';
            return;
        }
        
        suggestions.innerHTML = '';
        currentSuggestions.forEach((cap, index) => {
            const item = html`<div class="autocomplete-item" data-index="${index}">${cap}</div>`;
            item.addEventListener('click', () => selectCapability(cap));
            item.addEventListener('mouseenter', () => {
                selectedIndex = index;
                updateSelection();
            });
            suggestions.appendChild(item);
        });
        
        suggestions.style.display = 'block';
        updateSelection();
    }
    
    function updateSelection() {
        suggestions.querySelectorAll('.autocomplete-item').forEach((item, index) => {
            item.classList.toggle('selected', index === selectedIndex);
        });
    }
    
    function selectCapability(capability) {
        input.value = '';
        suggestions.style.display = 'none';
        
        // Add the capability
        addCapability(email, capability).then(() => {
            return fetchCapabilitiesList();
        }).then(() => {
            renderTable();
        }).catch(error => {
            showError(error.message);
        });
    }
    
    input.addEventListener('input', (e) => {
        showSuggestions(e.target.value);
    });
    
    input.addEventListener('focus', () => {
        // Show all available capabilities when input is focused
        showSuggestions('');
    });
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, currentSuggestions.length - 1);
            updateSelection();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, -1);
            updateSelection();
        } else if (e.key === 'Enter' && selectedIndex >= 0) {
            e.preventDefault();
            selectCapability(currentSuggestions[selectedIndex]);
        } else if (e.key === 'Escape') {
            suggestions.style.display = 'none';
        }
    });
    
    // Hide suggestions when clicking outside
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            suggestions.style.display = 'none';
        }
    });
    
    return container;
}

function createTableRow(email, capabilities, isNew = false) {
    const userCaps = new Set(capabilities || []);
    
    // Create email cell
    const emailCell = html`<td></td>`;
    if (isNew) {
        const emailInput = html`<input type="email" class="edit-input" placeholder="user@example.com" value="">`;
        emailCell.appendChild(emailInput);
        
        emailInput.addEventListener('blur', () => {
            const newEmail = emailInput.value.trim().toLowerCase();
            const row = emailInput.closest('tr');
            
            if (newEmail) {
                // Update the row's data-email
                row.setAttribute('data-email', newEmail);
                // Update all capability badges and inputs
                row.querySelectorAll('[data-email]').forEach(el => {
                    el.setAttribute('data-email', newEmail);
                });
                // Update autocomplete to use new email and current capabilities
                const autocompleteContainer = row.querySelector('.capability-input-container');
                if (autocompleteContainer) {
                    const currentCaps = usersData[newEmail] || [];
                    const newContainer = createAutocompleteInput(newEmail, currentCaps);
                    autocompleteContainer.replaceWith(newContainer);
                }
            } else {
                // Remove empty rows
                row.remove();
            }
        });
    } else {
        emailCell.textContent = email;
    }
    
    // Create capabilities cell
    const capabilitiesCell = html`<td></td>`;
    const badgesContainer = html`<div class="capabilities-badges-cell"></div>`;
    
    // Calculate all capabilities (explicit + implicit)
    const allUserCapabilities = new Set();
    userCaps.forEach(cap => {
        const implied = getImpliedCapabilities(cap);
        implied.forEach(impliedCap => allUserCapabilities.add(impliedCap));
    });
    
    // Add all capability badges (in graph order) - both explicit and implicit
    getOrderedCapabilities().forEach(cap => {
        if (allUserCapabilities.has(cap)) {
            // A capability is implicit if it's in allUserCapabilities but not in userCaps (explicit)
            const isImplicit = !userCaps.has(cap);
            const badge = createCapabilityBadge(email, cap, isImplicit);
            badgesContainer.appendChild(badge);
        }
    });
    
    // Add autocomplete input
    const autocompleteContainer = createAutocompleteInput(email, capabilities);
    badgesContainer.appendChild(autocompleteContainer);
    
    capabilitiesCell.appendChild(badgesContainer);
    
    // Create remove button cell
    const removeCell = html`<td class="cell-center"></td>`;
    const removeBtn = html`<button type="button" class="btn-remove-x" tabindex="-1">×</button>`;
    removeBtn.addEventListener('click', async () => {
        const row = removeBtn.closest('tr');
        const rowEmail = row.getAttribute('data-email');
        
        if (isNew || !rowEmail) {
            row.remove();
            return;
        }
        
        if (!confirm(`Remove all capabilities for ${rowEmail}?`)) {
            return;
        }
        
        try {
            await setCapabilities(rowEmail, []);
            await fetchCapabilitiesList();
            renderTable();
        } catch (error) {
            showError(error.message);
        }
    });
    removeCell.appendChild(removeBtn);
    
    // Create the row
    const row = html`<tr data-email="${email || ''}"></tr>`;
    row.appendChild(emailCell);
    row.appendChild(capabilitiesCell);
    row.appendChild(removeCell);
    
    return row;
}

async function setCapabilities(email, capabilities) {
    try {
        const response = await fetch(`${prefix}/manage_capabilities/set`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, capabilities }),
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Failed to set capabilities: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error setting capabilities:', error);
        throw error;
    }
}

function renderTable() {
    const tbody = document.getElementById('capabilitiesTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    // Render existing users
    Object.entries(usersData).forEach(([email, capabilities]) => {
        const row = createTableRow(email, capabilities, false);
        tbody.appendChild(row);
    });
}

function addNewRow() {
    const tbody = document.getElementById('capabilitiesTableBody');
    if (!tbody) return;
    
    // Create row with empty email (no placeholder value)
    const row = createTableRow('', [], true);
    tbody.appendChild(row);
    
    // Focus on the email input
    const emailInput = row.querySelector('input[type="email"]');
    if (emailInput) {
        emailInput.focus();
    }
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    if (!errorDiv) return;
    
    errorDiv.textContent = `Error: ${message}`;
    errorDiv.style.display = 'block';
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

function showLoading() {
    const loadingDiv = document.getElementById('loadingMessage');
    const contentDiv = document.getElementById('capabilitiesContent');
    const errorDiv = document.getElementById('errorMessage');
    
    if (loadingDiv) loadingDiv.style.display = 'block';
    if (contentDiv) contentDiv.style.display = 'none';
    if (errorDiv) errorDiv.style.display = 'none';
}

function showContent() {
    const loadingDiv = document.getElementById('loadingMessage');
    const contentDiv = document.getElementById('capabilitiesContent');
    
    if (loadingDiv) loadingDiv.style.display = 'none';
    if (contentDiv) contentDiv.style.display = 'block';
}

export async function manageCapabilities(oauthPrefix = '') {
    prefix = oauthPrefix || '';
    showLoading();
    
    try {
        await fetchCapabilitiesList();
        renderTable();
        showContent();
        
        // Handle "Add User" button
        const addUserBtn = document.getElementById('addUserBtn');
        if (addUserBtn) {
            addUserBtn.addEventListener('click', () => {
                addNewRow();
            });
        }
    } catch (error) {
        showError(error.message || 'Failed to load capabilities');
        document.getElementById('loadingMessage').style.display = 'none';
    }
}
