import { html } from './common.js';
import {
    createAuthorsSection,
    createDetailsSection,
    createReleasesSection,
    getScoreClass
} from './paper.js';

function setResults(...elements) {
    const container = document.getElementById('worksetContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

async function fetchWorksets(offset = 0, size = 100) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        size: size.toString(),
        expand_links: true,
    });

    const url = `/api/v1/work/view?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function createInfoValue(value) {
    if (value === null || value === undefined) {
        return html`<span class="info-null">null</span>`;
    }
    if (typeof value === 'object' && !Array.isArray(value)) {
        // Recursively create a table for nested objects
        return createInfoTable(value);
    }
    if (Array.isArray(value)) {
        // For arrays, stringify them
        return html`<span>${JSON.stringify(value)}</span>`;
    }
    return html`<span>${String(value)}</span>`;
}

function createInfoTable(info) {
    if (!info || Object.keys(info).length === 0) {
        return null;
    }

    const rows = Object.entries(info).map(([key, value]) => {
        return html`
            <tr>
                <td class="info-key">${key}</td>
                <td class="info-value">${createInfoValue(value)}</td>
            </tr>
        `;
    });

    return html`
        <table class="info-table">
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

function createWorksetPaperElement(paper) {
    const info = paper.info || {};

    // Get the first link URL if available
    const firstLink = paper.links && paper.links.length > 0 ? paper.links[0] : null;
    const titleUrl = firstLink ? firstLink.link : null;

    // Get the first PDF link if available
    const firstPdfLink = paper.links?.find(link => link.type?.toLowerCase().includes('pdf'));
    const pdfBadge = firstPdfLink
        ? html`<a href="${firstPdfLink.link}" target="_blank" class="badge pdf" title="${firstPdfLink.link}">PDF</a>`
        : null;

    const titleContent = titleUrl
        ? html`<a href="${titleUrl}" target="_blank" class="paper-title-link">${paper.title ?? 'Untitled'}</a>`
        : html`<span>${paper.title ?? 'Untitled'}</span>`;

    const titleWithEdit = html`
        <h3 class="paper-title" style="display: flex; align-items: center;">
            ${titleContent}
            ${pdfBadge}
        </h3>
    `;

    const infoTable = createInfoTable(info);

    return html`
        <div class="paper-content">
            ${titleWithEdit}
            ${createAuthorsSection(paper.authors)}
            ${createReleasesSection(paper.releases)}
            ${createDetailsSection(paper)}
            ${infoTable}
        </div>
    `;
}

export function createWorksetElement(scoredWorkset) {
    // scoredWorkset is Scored[PaperWorkingSet]
    // It has: { score: float, value: PaperWorkingSet }
    const score = scoredWorkset.score;
    const workset = scoredWorkset.value;
    const current = workset.current;
    const collected = workset.collected || [];

    // current and collected are all Paper objects with key, info, score fields
    // For display, we pair each paper with its tab label and score
    const allPapers = [];
    if (current) {
        allPapers.push({ paper: current, tabKey: 'current', score: score });
    }
    
    // Add collected papers with their own keys as tab labels
    collected.forEach(paper => {
        allPapers.push({ paper, tabKey: paper.key, score: paper.score });
    });
    
    // If no papers at all, return empty
    if (allPapers.length === 0) {
        return html`<div class="workset-item"><div class="workset-content">No papers in this workset.</div></div>`;
    }
    
    const tabButtons = allPapers.map(({ paper, tabKey }, tabIndex) => {
        const key = tabKey;
        const info = paper.info || {};
        let tabTitle;
        let tabSubtitle = null;
        
        if (key.includes(';')) {
            // If key contains ';', display "pdf" as the title
            tabTitle = 'pdf';
        } else if (key.includes(':')) {
            // If key is of form x:y, display y in smaller type under x
            const parts = key.split(':');
            tabTitle = parts[0];
            tabSubtitle = parts.slice(1).join(':'); // Handle multiple colons
        } else {
            // Regular key
            tabTitle = key;
        }
        
        // Determine badge classes based on paper content
        const badgeClasses = [];
        if (paper.releases && paper.releases.length > 0) {
            badgeClasses.push('has-releases');
        }
        // Check if any author has affiliations
        const hasAffiliations = paper.authors?.some(author => 
            author.affiliations && author.affiliations.length > 0
        );
        if (hasAffiliations) {
            badgeClasses.push('has-affiliations');
        }
        if (paper.abstract) {
            badgeClasses.push('has-abstract');
        }
        // Check for PDF link (same logic as PDF badge next to title)
        const hasPdfLink = paper.links?.some(link => link.type?.toLowerCase().includes('pdf'));
        if (hasPdfLink) {
            badgeClasses.push('has-pdf');
        }
        
        const buttonContent = tabSubtitle
            ? html`
                <span class="tab-title">${tabTitle}</span>
                <span class="tab-subtitle">${tabSubtitle}</span>
            `
            : html`<span class="tab-title">${tabTitle}</span>`;
        
        const allClasses = ['tab-button', ...badgeClasses, tabIndex === 0 ? 'active' : ''].filter(Boolean).join(' ');
        const button = html`<button class="${allClasses}" data-tab-index="${tabIndex}">${buttonContent}</button>`;
        return button;
    });

    const tabContent = allPapers.map(({ paper }, tabIndex) => {
        const content = html`
            <div class="tab-content ${tabIndex === 0 ? 'active' : ''}" data-tab-index="${tabIndex}">
                ${createWorksetPaperElement(paper)}
            </div>
        `;
        return content;
    });

    const tabsContainer = html`
        <div class="workset-tabs">
            <div class="tab-buttons">${tabButtons}</div>
            <div class="tab-contents">${tabContent}</div>
        </div>
    `;

    // Create the score band on the left
    const initialScore = allPapers[0].score;
    const scoreValueElement = html`<div class="score-value">${Math.round(initialScore)}</div>`;
    const scoreBand = html`
        <div class="score-band ${getScoreClass(initialScore)}">
            ${scoreValueElement}
        </div>
    `;

    // Create the workset item structure
    const worksetItem = html`
        <div class="workset-item">
            <div class="workset-content">
                ${scoreBand}
                ${tabsContainer}
            </div>
        </div>
    `;

    // Add tab switching functionality
    const buttons = worksetItem.querySelectorAll('.tab-button');
    const contents = worksetItem.querySelectorAll('.tab-content');
    
    let currentTabIndex = 0;
    let isFocused = false;
    
    function switchToTab(index) {
        if (index < 0 || index >= buttons.length) return;
        
        // Remove active class from all buttons and contents
        buttons.forEach(btn => btn.classList.remove('active'));
        contents.forEach(content => content.classList.remove('active'));
        
        // Add active class to selected button and corresponding content
        buttons[index].classList.add('active');
        contents[index].classList.add('active');
        
        // Update the score to match the active paper
        const newScore = allPapers[index].score;
        scoreValueElement.textContent = Math.round(newScore);
        
        // Update score band color class
        scoreBand.className = `score-band ${getScoreClass(newScore)}`;
        
        // Update current tab index
        currentTabIndex = index;
    }
    
    function setFocused(value) {
        isFocused = value;
        if (value) {
            worksetItem.classList.add('workset-focused');
            // Remove focus from other worksets
            document.querySelectorAll('.workset-item.workset-focused').forEach(item => {
                if (item !== worksetItem) {
                    item.classList.remove('workset-focused');
                    if (item._setFocused) {
                        item._setFocused(false);
                    }
                }
            });
        } else {
            worksetItem.classList.remove('workset-focused');
        }
    }
    
    buttons.forEach((button, idx) => {
        button.addEventListener('click', () => {
            switchToTab(idx);
            setFocused(true);
        });
    });
    
    // Mark workset as focused when clicking anywhere in it
    worksetItem.addEventListener('click', (e) => {
        if (worksetItem.contains(e.target)) {
            setFocused(true);
        }
    });
    
    // Add keyboard navigation
    function handleKeyDown(event) {
        // Only handle if this workset is focused
        if (!isFocused) return;
        
        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            switchToTab(Math.max(0, currentTabIndex - 1));
        } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            switchToTab(Math.min(buttons.length - 1, currentTabIndex + 1));
        }
    }
    
    // Add event listener to document for keyboard navigation
    document.addEventListener('keydown', handleKeyDown);
    
    // Store functions on the workset item
    worksetItem._keyboardHandler = handleKeyDown;
    worksetItem._setFocused = setFocused;

    return worksetItem;
}

function renderWorksets(data) {
    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                No worksets found.
            </div>
        `;
        setResults(noResults);
        return;
    }

    const worksetElements = data.results.map((scoredWorkset, index) => 
        createWorksetElement(scoredWorkset, index)
    );
    const worksetList = html`<div class="workset-list">${worksetElements}</div>`;

    setResults(worksetList);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading worksets: ${error.message}</div>`);
}

export async function displayWorksets() {
    displayLoading();

    try {
        const data = await fetchWorksets();
        renderWorksets(data);
    } catch (error) {
        console.error('Failed to load worksets:', error);
        displayError(error);
    }
}
