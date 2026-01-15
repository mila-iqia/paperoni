import { html, toggle, join } from './common.js';

let isValidator = false;
let showValidationButtons = false;

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
    });

    const url = `/api/v1/work/view?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function formatAuthorsWithAffiliations(authors) {
    const institutionMap = new Map();
    let institutionCounter = 1;

    authors.forEach(author => {
        const affiliations = author.affiliations ?? [];
        affiliations.forEach(aff => {
            const name = aff.display_name || aff.name || '';
            if (name && !institutionMap.has(name)) {
                institutionMap.set(name, institutionCounter++);
            }
        });
    });

    const authorData = authors.map(author => {
        const name = author.display_name ?? 'Unknown';
        const affiliations = author.affiliations ?? [];
        const affNumbers = affiliations
            .map(aff => {
                const affName = aff.display_name || aff.name || '';
                return institutionMap.get(affName);
            })
            .filter(num => num !== undefined)
            .sort((a, b) => a - b);

        return { name, affNumbers };
    });

    return {
        authorData,
        institutions: Array.from(institutionMap.entries()).sort((a, b) => a[1] - b[1])
    };
}

function formatDate(dateString, precision) {
    if (!dateString) return null;
    const parts = dateString.split('-');
    const year = parts[0];
    const month = parts[1].padStart(2, '0');
    const day = parts[2].padStart(2, '0');

    if (precision === 2 || precision === '2') {
        return `${year}`;
    } else if (precision === 1 || precision === '1') {
        return `${year}-${month}`;
    } else {
        return `${year}-${month}-${day}`;
    }
}

function formatRelease(release) {
    const date = release.venue?.date
        ? formatDate(release.venue.date, release.venue.date_precision)
        : null;
    const venueName = release.venue?.name ?? null;
    const status = release.status ?? null;
    return { date, venueName, status };
}

function sortReleasesByDate(releases) {
    return [...releases].sort((a, b) => {
        const parseDate = (dateString) => {
            if (!dateString) return new Date(0);
            const parts = dateString.split('-');
            if (parts.length === 3) {
                return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
            }
            return new Date(dateString);
        };
        const dateA = parseDate(a.venue?.date);
        const dateB = parseDate(b.venue?.date);
        return dateB - dateA;
    });
}

function createAuthorsSection(authors) {
    if (!authors || authors.length === 0) {
        return html`<div class="paper-authors-container"><div class="paper-authors">No authors</div></div>`;
    }
    const { authorData, institutions } = formatAuthorsWithAffiliations(authors);
    const authorElements = authorData.map(({ name, affNumbers }) => {
        const superscriptsWithCommas = affNumbers.length > 0
            ? html`<sup>${join(',', affNumbers)}</sup>`
            : null;
        const authorSpan = html`<span class="author-name" data-affiliations="${affNumbers.join(',')}" data-name="${name}">${name}${superscriptsWithCommas}</span>`;
        return authorSpan;
    });
    const authorNodes = join(', ', authorElements);
    const institutionElements = institutions.map(([name, num]) => {
        const instSpan = html`<span class="institution-item" data-affiliation="${num}" data-name="${name}"><sup>${num}</sup>${name}</span>`;
        return instSpan;
    });
    const institutionsHtml = institutions.length > 0
        ? html`<div class="paper-institutions">${join('; ', institutionElements)}</div>`
        : null;
    return html`
        <div class="paper-authors-container">
            <div class="paper-authors">${authorNodes}</div>
            ${institutionsHtml}
        </div>
    `;
}

function createReleasesSection(releases) {
    if (!releases || releases.length === 0) {
        return html`<div class="paper-meta-item"><div class="paper-releases">No releases</div></div>`;
    }
    const sortedReleases = sortReleasesByDate(releases);
    const releaseItems = sortedReleases.map(release => {
        const { date, venueName, status } = formatRelease(release);
        const venueSpan = html`<span class="release-venue">${venueName ?? 'Unknown'}</span>`;
        let dateElement;
        if (date && date.length >= 4) {
            const year = date.substring(0, 4);
            const rest = date.substring(4);
            dateElement = html`<strong class="release-date">${year}${rest}</strong>`;
        } else {
            dateElement = html`<strong class="release-date">${date ?? '????-??-??'}</strong>`;
        }
        const statusSpan = status
            ? html`<span class="release-status">${status}</span>`
            : null;
        return html`
            <div class="release-item">
                ${dateElement}
                ${statusSpan}
                ${venueSpan}
            </div>
        `;
    });
    return html`
        <div class="paper-meta-item">
            <div class="paper-releases">${releaseItems}</div>
        </div>
    `;
}

function extractDomain(url) {
    try {
        const hostname = new URL(url).hostname;
        // Remove www. prefix and get the domain without TLD
        const parts = hostname.replace(/^www\./, '').split('.');
        // Return the main domain name (without TLD like .com, .org, .net, etc.)
        return parts.length > 1 ? parts.slice(0, -1).join('.') : parts[0];
    } catch {
        return null;
    }
}

function createLinksSection(links) {
    if (!links || links.length === 0) return null;

    const linkBadges = links.map(link => {
        const linkType = link.type ?? 'unknown';
        const linkUrl = link.link;
        const domain = extractDomain(linkUrl);
        
        // Check if the domain name (minus TLD) is already in the type
        const typeContainsDomain = domain && linkType.toLowerCase().includes(domain.toLowerCase());
        const badgeText = (domain && !typeContainsDomain) ? `${linkType} (${domain})` : linkType;
        
        return html`<a href="${linkUrl}" target="_blank" class="badge link" title="${linkUrl}">${badgeText}</a>`;
    });

    return html`<div class="paper-links">${linkBadges}</div>`;
}

function createDetailsSection(paper) {
    const abstractHtml = paper.abstract ? html`<div class="paper-abstract">${paper.abstract}</div>` : null;
    const topicsHtml = paper.topics && paper.topics.length > 0
        ? html`<div class="paper-topics">${paper.topics.map(topic =>
            html`<span class="badge topic">${topic.name ?? topic.display_name ?? 'Unknown'}</span>`
        )}</div>`
        : null;
    const linksHtml = createLinksSection(paper.links);

    return toggle`
        <div class="paper-collapsible-section">
            <button class="toggle-details-button" toggler>
                <span class="item-toggle">▶</span> Details
            </button>
            <div class="details-content" toggled>
                ${abstractHtml}
                ${topicsHtml}
                ${linksHtml}
            </div>
        </div>
    `;
}

function createInfoTable(info) {
    if (!info || Object.keys(info).length === 0) {
        return null;
    }

    const rows = Object.entries(info).map(([key, value]) => {
        const valueStr = typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
        return html`
            <tr>
                <td class="info-key">${key}</td>
                <td class="info-value">${valueStr}</td>
            </tr>
        `;
    });

    return html`
        <table class="info-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

function createPaperElement(paperInfo) {
    const paper = paperInfo.paper;
    const key = paperInfo.key;
    const info = paperInfo.info || {};
    const score = paperInfo.score;

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

function createWorksetElement(scoredWorkset, index) {
    // scoredWorkset is Scored[PaperWorkingSet]
    // It has: { score: float, value: PaperWorkingSet }
    const score = scoredWorkset.score;
    const workset = scoredWorkset.value;
    const current = workset.current;
    const collected = workset.collected || [];

    // Create current paper as PaperInfo (only if current exists)
    const allPapers = [];
    if (current) {
        const currentPaperInfo = {
            paper: current,
            key: 'current',
            info: {},
            score: score
        };
        allPapers.push(currentPaperInfo);
    }
    
    // Add collected papers
    allPapers.push(...collected);
    
    // If no papers at all, return empty
    if (allPapers.length === 0) {
        return html`<div class="workset-item"><div class="workset-content">No papers in this workset.</div></div>`;
    }
    
    const tabButtons = allPapers.map((paperInfo, tabIndex) => {
        const paper = paperInfo.paper;
        const key = paperInfo.key;
        const info = paperInfo.info || {};
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
        
        // Get the first key from info.refined_by if it exists
        let refinedByKey = null;
        if (info.refined_by && typeof info.refined_by === 'object') {
            const keys = Object.keys(info.refined_by);
            if (keys.length > 0) {
                refinedByKey = keys[0];
            }
        }
        
        // Combine title with refined_by key using "/" separator
        const displayTitle = refinedByKey ? `${tabTitle} / ${refinedByKey}` : tabTitle;
        
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
                <span class="tab-title">${displayTitle}</span>
                <span class="tab-subtitle">${tabSubtitle}</span>
            `
            : html`<span class="tab-title">${displayTitle}</span>`;
        
        const allClasses = ['tab-button', ...badgeClasses, tabIndex === 0 ? 'active' : ''].filter(Boolean).join(' ');
        const button = html`<button class="${allClasses}" data-tab-index="${tabIndex}">${buttonContent}</button>`;
        return button;
    });

    const tabContent = allPapers.map((paperInfo, tabIndex) => {
        const content = html`
            <div class="tab-content ${tabIndex === 0 ? 'active' : ''}" data-tab-index="${tabIndex}">
                ${createPaperElement(paperInfo)}
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
    const scoreValueElement = html`<div class="score-value">${allPapers[0].score.toFixed(2)}</div>`;
    const scoreBand = html`
        <div class="score-band">
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
        const activePaper = allPapers[index];
        scoreValueElement.textContent = activePaper.score.toFixed(2);
        
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

export async function displayWorksets(hasValidateCapability = false, enableValidationButtons = false) {
    isValidator = hasValidateCapability;
    showValidationButtons = enableValidationButtons;

    displayLoading();

    try {
        const data = await fetchWorksets();
        renderWorksets(data);
    } catch (error) {
        console.error('Failed to load worksets:', error);
        displayError(error);
    }
}
