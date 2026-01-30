import { html, showToast } from './common.js';

let mainFocuses = [];
let autoFocuses = [];

export function init() {
    loadFocuses();
    setupTabs();

    document.getElementById('addMainFocusBtn').addEventListener('click', () => {
        addFocusRow('main', undefined, true);
    });

    document.getElementById('addAutoFocusBtn').addEventListener('click', () => {
        addFocusRow('auto', undefined, true);
    });

    document.getElementById('saveMainFocusesBtn').addEventListener('click', () => {
        saveFocuses('main');
    });

    document.getElementById('saveAutoFocusesBtn').addEventListener('click', () => {
        saveFocuses('auto');
    });

    document.getElementById('autogenerateFocusesBtn').addEventListener('click', () => {
        autogenerateFocuses();
    });
}

function setupTabs() {
    const tabs = document.querySelectorAll('.focuses-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            
            // Update active tab button
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Update active tab content
            document.querySelectorAll('.focuses-tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabId}-tab`).classList.add('active');
        });
    });
}

async function loadFocuses() {
    const mainTbody = document.querySelector('#mainFocusesTable tbody');
    const autoTbody = document.querySelector('#autoFocusesTable tbody');
    mainTbody.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';
    autoTbody.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';

    try {
        const response = await fetch('/api/v1/focuses');
        if (!response.ok) throw new Error('Failed to load focuses');
        
        const data = await response.json();
        
        // Handle the new format with main and auto sublists
        mainFocuses = data.main || [];
        autoFocuses = data.auto || [];

        renderTable('main', mainFocuses);
        renderTable('auto', autoFocuses);

    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

function parseFocus(focus) {
    if (typeof focus === 'string') {
        let s = focus;
        const drive_discovery = s.startsWith("!");
        if (drive_discovery) {
            s = s.substring(1);
        }
        const parts = s.split("::");
        if (parts.length >= 3) {
            return {
                type: parts[0].trim(),
                name: parts[1].trim(),
                score: parseFloat(parts[2].trim()),
                drive_discovery: drive_discovery
            };
        }
    }
    return focus;
}

function renderTable(section, focuses) {
    const tableId = section === 'main' ? 'mainFocusesTable' : 'autoFocusesTable';
    const tbody = document.querySelector(`#${tableId} tbody`);
    tbody.innerHTML = '';

    focuses.forEach(f => {
        const parsed = parseFocus(f);
        if (parsed) {
            addFocusRow(section, parsed);
        }
    });
}

function addFocusRow(section, focus = { type: 'author', name: '', score: 1, drive_discovery: false }, scrollToRow = false) {
    const tableId = section === 'main' ? 'mainFocusesTable' : 'autoFocusesTable';
    const tbody = document.querySelector(`#${tableId} tbody`);
    const row = document.createElement('tr');
    
    row.innerHTML = `
        <td>
            <select class="focus-type edit-input">
                <option value="author" ${focus.type === 'author' ? 'selected' : ''}>Author</option>
                <option value="institution" ${focus.type === 'institution' ? 'selected' : ''}>Institution</option>
            </select>
        </td>
        <td>
            <input type="text" class="focus-name edit-input" value="${focus.name || ''}" placeholder="Name">
        </td>
        <td>
            <input type="number" step="1" class="focus-score edit-input" value="${focus.score}" placeholder="Score">
        </td>
        <td class="cell-center">
            <input type="checkbox" class="focus-drive" ${focus.drive_discovery ? 'checked' : ''}>
        </td>
        <td class="cell-center">
            <button class="btn-remove-x">×</button>
        </td>
    `;

    row.querySelector('.btn-remove-x').addEventListener('click', () => row.remove());
    
    tbody.appendChild(row);
    
    if (scrollToRow) {
        // Scroll to the new row
        row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Focus the type select as it's the first field
        row.querySelector('.focus-type').focus();
    }
}

function collectFocusesFromTable(tableId) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    return rows.map(row => {
        return {
            type: row.querySelector('.focus-type').value,
            name: row.querySelector('.focus-name').value.trim(),
            score: parseFloat(row.querySelector('.focus-score').value),
            drive_discovery: row.querySelector('.focus-drive').checked
        };
    }).filter(f => f.name); // Filter empty names
}

async function saveFocuses(section) {
    const btnId = section === 'main' ? 'saveMainFocusesBtn' : 'saveAutoFocusesBtn';
    
    const mainFocusesList = collectFocusesFromTable('mainFocusesTable');
    const autoFocusesList = collectFocusesFromTable('autoFocusesTable');

    const btn = document.getElementById(btnId);
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/v1/focuses', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ main: mainFocusesList, auto: autoFocusesList })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to save');
        }

        showToast('Focuses saved successfully!', 'success');
    } catch (error) {
        showToast(`Error saving focuses: ${error.message}`, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function autogenerateFocuses() {
    const btn = document.getElementById('autogenerateFocusesBtn');
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/v1/focus/auto', { method: 'POST' });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || err.message || 'Failed to autogenerate');
        }

        const data = await response.json();
        
        // The endpoint returns the full Focuses object with auto populated
        const newAutoFocuses = data.auto || [];
        
        // Render the new auto focuses
        renderTable('auto', newAutoFocuses);
        
        showToast(`Autogenerated ${newAutoFocuses.length} focus(es).`, 'success');
    } catch (error) {
        showToast(`Error autogenerating focuses: ${error.message}`, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}
