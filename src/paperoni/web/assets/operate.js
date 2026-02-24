import { debounce, html } from './common.js';
import {
    clearSearchForm,
    getSearchParams,
    searchParamsToFlags,
} from './search-form.js';
import { createWorksetPaperElement, createDiffViewWithTabs } from './workset.js';

const PAGE_SIZE = 100;
const MONACO_CDN = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min';
const STORAGE_KEY_BLOCKS = 'operate.blocks';
const STORAGE_KEY_INDEX = 'operate.index';
const DEFAULT_OPERATION = `# Write body of operate(paper)`;

let monacoEditor = null;
let blocks = [];
let currentIndex = 0;
/** Copy of the operation used for auto-search (not the live editor content) */
let searchBlock = '';

function loadFromStorage() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY_BLOCKS);
        blocks = stored ? JSON.parse(stored) : [DEFAULT_OPERATION];
        if (!Array.isArray(blocks) || blocks.length === 0) {
            blocks = [DEFAULT_OPERATION];
        }
        const idx = parseInt(localStorage.getItem(STORAGE_KEY_INDEX) || '0', 10);
        currentIndex = Math.max(0, Math.min(idx, blocks.length - 1));
    } catch {
        blocks = [DEFAULT_OPERATION];
        currentIndex = 0;
    }
}

function saveToStorage() {
    try {
        localStorage.setItem(STORAGE_KEY_BLOCKS, JSON.stringify(blocks));
        localStorage.setItem(STORAGE_KEY_INDEX, String(currentIndex));
    } catch (e) {
        console.warn('Failed to save blocks to localStorage:', e);
    }
}

function getBlockLabel(block, index) {
    const firstLine = (block || '').trim().split('\n')[0]?.trim() || '(empty)';
    const short = firstLine.length > 50 ? firstLine.slice(0, 47) + '...' : firstLine;
    return `${index + 1}: ${short}`;
}

function setResults(...elements) {
    const container = document.getElementById('operateResultsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

function loadMonacoEditor() {
    return new Promise((resolve) => {
        const req = window.require;
        if (!req) {
            console.error('Monaco loader not found. Is the CDN script loaded?');
            resolve(null);
            return;
        }
        req.config({
            paths: {
                vs: `${MONACO_CDN}/vs`,
            },
            'vs/nls': { availableLanguages: { '*': '' } },
        });
        req(['vs/editor/editor.main'], function () {
            const container = document.getElementById('operationEditor');
            if (!container) {
                resolve(null);
                return;
            }
            monacoEditor = window.monaco.editor.create(container, {
                value: blocks[currentIndex] ?? '',
                language: 'python',
                theme: 'vs',
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 13,
                lineNumbers: 'on',
                wordWrap: 'on',
                automaticLayout: true,
                quickSuggestions: false,
                suggestOnTriggerCharacters: false,
                acceptSuggestionOnCommitCharacter: false,
            });
            monacoEditor.onDidChangeModelContent(() => {
                if (currentIndex >= 0 && currentIndex < blocks.length) {
                    blocks[currentIndex] = monacoEditor.getValue();
                    saveToStorage();
                    refreshDropdownLabels();
                }
            });
            resolve(monacoEditor);
        });
    });
}

function refreshDropdownLabels() {
    const sel = document.getElementById('operateBlocksSelect');
    if (!sel) return;
    const selected = sel.value;
    sel.innerHTML = '';
    blocks.forEach((block, i) => {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = getBlockLabel(block, i);
        sel.appendChild(opt);
    });
    sel.value = String(currentIndex);
}

function syncEditorToBlock() {
    if (monacoEditor && currentIndex >= 0 && currentIndex < blocks.length) {
        blocks[currentIndex] = monacoEditor.getValue();
        saveToStorage();
    }
}

function selectBlock(index) {
    syncEditorToBlock();
    currentIndex = Math.max(0, Math.min(index, blocks.length - 1));
    if (monacoEditor) {
        monacoEditor.setValue(blocks[currentIndex] ?? '');
    }
    searchBlock = blocks[currentIndex] ?? '';
    const sel = document.getElementById('operateBlocksSelect');
    if (sel) sel.value = String(currentIndex);
    refreshDropdownLabels();
    updateDeleteButtonState();
    runSearch();
}

function addBlock(content) {
    syncEditorToBlock();
    blocks.push(content);
    currentIndex = blocks.length - 1;
    if (monacoEditor) {
        monacoEditor.setValue(content);
    }
    saveToStorage();
    refreshDropdownLabels();
    updateDeleteButtonState();
}

function cloneBlock() {
    const content = monacoEditor ? monacoEditor.getValue() : (blocks[currentIndex] ?? '');
    addBlock(content);
}

function deleteBlock() {
    if (blocks.length <= 1) return;
    syncEditorToBlock();
    blocks.splice(currentIndex, 1);
    const nextIndex = currentIndex >= blocks.length ? blocks.length - 1 : currentIndex;
    currentIndex = nextIndex;
    if (monacoEditor) {
        monacoEditor.setValue(blocks[currentIndex] ?? '');
    }
    saveToStorage();
    refreshDropdownLabels();
    const sel = document.getElementById('operateBlocksSelect');
    if (sel) sel.value = String(currentIndex);
    updateDeleteButtonState();
}

function updateDeleteButtonState() {
    const btn = document.getElementById('operateBlockDelete');
    if (btn) btn.disabled = blocks.length <= 1;
}

async function fetchOperateResults(operation, searchParams) {
    const flags = searchParamsToFlags(searchParams);
    const body = {
        operation: operation.trim(),
        title: searchParams.title || undefined,
        author: searchParams.author || undefined,
        institution: searchParams.institution || undefined,
        venue: searchParams.venue || undefined,
        start_date: searchParams.start_date || undefined,
        end_date: searchParams.end_date || undefined,
        flags: flags.length ? flags : undefined,
        offset: 0,
        limit: PAGE_SIZE,
        expand_links: true,
    };

    const response = await fetch('/api/v1/operate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
            const errBody = await response.json();
            if (errBody.detail) {
                detail = typeof errBody.detail === 'string'
                    ? errBody.detail
                    : JSON.stringify(errBody.detail);
            }
        } catch {
            // ignore
        }
        const err = new Error(detail);
        err.detail = detail;
        throw err;
    }

    return await response.json();
}

function createOperateItem(paperDiff) {
    const current = paperDiff.current;
    const paperNew = paperDiff.new;

    let contentEl;
    if (!current) {
        contentEl = createWorksetPaperElement(paperNew, { excludeFromInfo: ['comments'] });
    } else if (!paperNew) {
        contentEl = createWorksetPaperElement(current, { excludeFromInfo: ['comments'] });
    } else {
        contentEl = createDiffViewWithTabs(current, paperNew);
    }

    return html`
        <div class="workset-item">
            <div class="workset-content">
                <div class="workset-tabs">
                    <div class="tab-contents" style="border: none; padding: 0;">
                        <div class="tab-content active" style="display: block;">
                            ${contentEl}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderResults(data) {
    if (!data.results || data.results.length === 0) {
        setResults(html`
            <div class="no-results">
                No papers to display. Run an operation to see results.
            </div>
        `);
        return;
    }

    const matched = data.results.filter(d => d.matched !== false);
    const unmatched = data.results.filter(d => d.matched === false);

    const matchedItems = matched.map(paperDiff => createOperateItem(paperDiff));
    const unmatchedItems = unmatched.map(paperDiff => createOperateItem(paperDiff));

    const matchedSection = matchedItems.length > 0
        ? html`
            <div class="operate-results-section">
                ${html`<div class="workset-list">${matchedItems}</div>`}
            </div>
        `
        : null;

    const unmatchedSection = unmatchedItems.length > 0
        ? html`
            <div class="operate-results-section">
                <h3 class="operate-section-header">Unmatched</h3>
                <div class="workset-list">${unmatchedItems.length} unmatched</div>
            </div>
        `
        : null;

    setResults(matchedSection, unmatchedSection);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    const detail = error.detail ?? error.message;
    setResults(html`
        <div class="error-message">
            <strong>Error</strong>
            <pre class="operate-traceback">${detail}</pre>
        </div>
    `);
}

function getOperationContent() {
    if (monacoEditor) {
        return monacoEditor.getValue();
    }
    return blocks[currentIndex] ?? '';
}

async function runSearch() {
    const operation = searchBlock.trim();
    const codeLines = operation.split('\n').filter(line => {
        const t = line.trim();
        return t && !t.startsWith('#');
    });
    if (codeLines.length === 0) {
        setResults(html`
            <div class="no-results">
                No operation to run. Enter code and click Update, or use Check to run the current block.
            </div>
        `);
        return;
    }

    displayLoading();

    try {
        const data = await fetchOperateResults(operation, getSearchParams());
        renderResults(data);
    } catch (error) {
        console.error('Operate failed:', error);
        displayError(error);
    }
}

const debouncedRunSearch = debounce(runSearch, 300);

export async function operatePapers() {
    loadFromStorage();

    const checkBtn = document.getElementById('operateCheckBtn');
    const form = document.getElementById('operateForm');
    const clearBtn = document.getElementById('clearSearch');
    const selectEl = document.getElementById('operateBlocksSelect');
    const updateBtn = document.getElementById('operateBlockUpdate');
    const newBtn = document.getElementById('operateBlockNew');
    const cloneBtn = document.getElementById('operateBlockClone');
    const deleteBtn = document.getElementById('operateBlockDelete');

    const titleInput = document.getElementById('title');
    const authorInput = document.getElementById('author');
    const institutionInput = document.getElementById('institution');
    const venueInput = document.getElementById('venue');
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    const validatedRadios = document.querySelectorAll('input[name="validated"]');
    const peerReviewedCheckbox = document.getElementById('peerReviewed');

    await loadMonacoEditor();

    searchBlock = blocks[currentIndex] ?? '';
    refreshDropdownLabels();
    updateDeleteButtonState();

    form.addEventListener('submit', (e) => {
        e.preventDefault();
    });

    function handleSearchChange() {
        debouncedRunSearch();
    }

    titleInput?.addEventListener('input', handleSearchChange);
    authorInput?.addEventListener('input', handleSearchChange);
    institutionInput?.addEventListener('input', handleSearchChange);
    venueInput?.addEventListener('input', handleSearchChange);
    startDateInput?.addEventListener('input', handleSearchChange);
    endDateInput?.addEventListener('input', handleSearchChange);
    validatedRadios?.forEach(radio => radio.addEventListener('change', handleSearchChange));
    peerReviewedCheckbox?.addEventListener('change', handleSearchChange);

    selectEl.addEventListener('change', () => {
        selectBlock(parseInt(selectEl.value, 10));
    });

    updateBtn.addEventListener('click', () => {
        syncEditorToBlock();
        searchBlock = getOperationContent();
        runSearch();
    });

    newBtn.addEventListener('click', () => {
        addBlock('');
    });

    cloneBtn.addEventListener('click', () => {
        cloneBlock();
    });

    deleteBtn.addEventListener('click', () => {
        deleteBlock();
    });

    debouncedRunSearch();

    checkBtn.addEventListener('click', async () => {
        syncEditorToBlock();
        const operation = getOperationContent().trim();
        const codeLines = operation.split('\n').filter(line => {
            const t = line.trim();
            return t && !t.startsWith('#');
        });
        if (codeLines.length === 0) {
            displayError(new Error('Please enter an operation'));
            return;
        }

        displayLoading();
        checkBtn.disabled = true;

        try {
            const data = await fetchOperateResults(operation, getSearchParams());
            renderResults(data);
        } catch (error) {
            console.error('Operate failed:', error);
            displayError(error);
        } finally {
            checkBtn.disabled = false;
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            clearSearchForm();
            handleSearchChange();
        });
    }
}
