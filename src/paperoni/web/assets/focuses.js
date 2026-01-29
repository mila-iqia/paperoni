import { html, showToast } from './common.js';

export function init() {
    loadFocuses();

    document.getElementById('addFocusBtn').addEventListener('click', () => {
        addFocusRow();
    });

    document.getElementById('saveFocusesBtn').addEventListener('click', () => {
        saveFocuses();
    });
}

async function loadFocuses() {
    const tbody = document.querySelector('#focusesTable tbody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';

    try {
        const response = await fetch('/api/v1/focuses');
        if (!response.ok) throw new Error('Failed to load focuses');
        
        const data = await response.json();
        
        let focuses = [];
        if (data.focuses) {
            focuses = data.focuses;
        } else if (Array.isArray(data)) {
            focuses = data;
        } else if (data._) { // Serieux sometimes uses _ for wrapped value
            focuses = data._;
        }

        renderTable(focuses);

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

function renderTable(focuses) {
    const tbody = document.querySelector('#focusesTable tbody');
    tbody.innerHTML = '';

    focuses.forEach(f => {
        const parsed = parseFocus(f);
        if (parsed) {
            addFocusRow(parsed);
        }
    });

    if (focuses.length === 0) {
        // No focuses
    }
}

function addFocusRow(focus = { type: 'author', name: '', score: 1, drive_discovery: false }) {
    const tbody = document.querySelector('#focusesTable tbody');
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
            <input type="number" step="0.1" class="focus-score edit-input" value="${focus.score}" placeholder="Score">
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
    
    // Scroll to the new row
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    // Focus the name input if it is empty, or type otherwise (though type is first)
    // Actually focusing the type makes sense as it is the first field
    row.querySelector('.focus-type').focus();
}

async function saveFocuses() {
    const tbody = document.querySelector('#focusesTable tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const newFocuses = rows.map(row => {
        return {
            type: row.querySelector('.focus-type').value,
            name: row.querySelector('.focus-name').value.trim(),
            score: parseFloat(row.querySelector('.focus-score').value),
            drive_discovery: row.querySelector('.focus-drive').checked
        };
    }).filter(f => f.name); // Filter empty names

    const btn = document.getElementById('saveFocusesBtn');
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/v1/focuses', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ focuses: newFocuses })
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
