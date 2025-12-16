import { html, toggle, debounce, join } from './common.js';

const PAGE_SIZE = 50;

let currentOffset = 0;
let currentParams = {};
let totalResults = 0;
let isValidator = false;
let showValidationButtons = false;

function setResults(...elements) {
    const container = document.getElementById('resultsContainer');
    container.innerHTML = '';
    elements.forEach(el => {
        if (el) container.appendChild(el);
    });
}

async function fetchSearchResults(params, offset = 0) {
    const queryParams = new URLSearchParams({
        offset: offset.toString(),
        size: PAGE_SIZE.toString(),
        expand_links: 'true'
    });

    // Add search parameters if they have values
    if (params.title) queryParams.append('title', params.title);
    if (params.author) queryParams.append('author', params.author);
    if (params.institution) queryParams.append('institution', params.institution);
    if (params.venue) queryParams.append('venue', params.venue);
    if (params.start_date) queryParams.append('start_date', params.start_date);
    if (params.end_date) queryParams.append('end_date', params.end_date);
    if (params.validated) queryParams.append('validated', params.validated);

    const url = `/api/v1/search?${queryParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

function formatAuthorsWithAffiliations(authors) {
    // Map institutions to unique numbers
    const institutionMap = new Map();
    let institutionCounter = 1;

    // First pass: collect all unique institutions
    authors.forEach(author => {
        const affiliations = author.affiliations ?? [];
        affiliations.forEach(aff => {
            const name = aff.display_name || aff.name || '';
            if (name && !institutionMap.has(name)) {
                institutionMap.set(name, institutionCounter++);
            }
        });
    });

    // Second pass: create author data with affiliation numbers
    const authorData = authors.map(author => {
        const name = author.display_name ?? 'Unknown';
        const affiliations = author.affiliations ?? [];
        const affNumbers = affiliations
            .map(aff => {
                const affName = aff.display_name || aff.name || '';
                return institutionMap.get(affName);
            })
            .filter(num => num !== undefined);

        return { name, affNumbers };
    });

    return {
        authorData,
        institutions: Array.from(institutionMap.entries()).sort((a, b) => a[1] - b[1])
    };
}

function formatDate(dateString, precision) {
    if (!dateString) return null;

    // Parse date string manually to avoid timezone issues
    // Assumes dateString is in YYYY-MM-DD format
    const parts = dateString.split('-');

    const year = parts[0];
    const month = parts[1].padStart(2, '0');
    const day = parts[2].padStart(2, '0');

    // DatePrecision: 0=day, 1=month, 2=year
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
        // Parse dates manually to avoid timezone issues
        const parseDate = (dateString) => {
            if (!dateString) return new Date(0);
            const parts = dateString.split('-');
            if (parts.length === 3) {
                // Create date in local timezone to avoid UTC conversion
                return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
            }
            return new Date(dateString); // Fallback
        };

        const dateA = parseDate(a.venue?.date);
        const dateB = parseDate(b.venue?.date);
        return dateB - dateA; // Most recent first
    });
}

function matchesSearch(text, searchTerm) {
    if (!searchTerm || !text) return false;
    return text.toLowerCase().includes(searchTerm.toLowerCase());
}

function createAuthorsSection(authors, searchParams = {}) {
    const { authorData, institutions } = formatAuthorsWithAffiliations(authors);

    // Find which institution numbers should be highlighted due to author search
    const highlightedInstNumbers = new Set();
    if (searchParams.author) {
        authorData.forEach(({ name, affNumbers }) => {
            if (matchesSearch(name, searchParams.author)) {
                affNumbers.forEach(num => highlightedInstNumbers.add(num));
            }
        });
    }

    // Find which institution numbers match the institution search
    const matchingInstNumbers = new Set();
    if (searchParams.institution) {
        institutions.forEach(([name, num]) => {
            if (matchesSearch(name, searchParams.institution)) {
                matchingInstNumbers.add(num);
            }
        });
    }

    // Create author elements with data attributes for affiliations
    const authorElements = authorData.map(({ name, affNumbers }) => {
        const superscriptsWithCommas = affNumbers.length > 0
            ? html`<sup>${join(',', affNumbers)}</sup>`
            : null;

        // Highlight if author name matches OR if any of their affiliations match institution search
        const authorNameMatches = matchesSearch(name, searchParams.author);
        const hasMatchingInstitution = affNumbers.some(num => matchingInstNumbers.has(num));
        const isMatch = authorNameMatches || hasMatchingInstitution;
        const authorSpan = html`<span class="author-name${isMatch ? ' search-match' : ''}" data-affiliations="${affNumbers.join(',')}" data-name="${name}">${name}${superscriptsWithCommas}</span>`;
        return authorSpan;
    });

    const authorNodes = join(', ', authorElements);

    // Create institution elements with data attributes
    const institutionElements = institutions.map(([name, num]) => {
        // Highlight if institution name matches OR if a matching author is affiliated with it
        const instNameMatches = matchesSearch(name, searchParams.institution);
        const hasMatchingAuthor = highlightedInstNumbers.has(num);
        const isMatch = instNameMatches || hasMatchingAuthor;
        const instSpan = html`<span class="institution-item${isMatch ? ' search-match' : ''}" data-affiliation="${num}" data-name="${name}"><sup>${num}</sup>${name}</span>`;
        return instSpan;
    });

    const institutionsHtml = institutions.length > 0
        ? html`<div class="paper-institutions">${join('; ', institutionElements)}</div>`
        : null;

    const container = html`
        <div class="paper-authors-container">
            <div class="paper-authors">${authorNodes}</div>
            ${institutionsHtml}
        </div>
    `;

    // Add hover event listeners for highlighting
    const authorSpans = container.querySelectorAll('.author-name');
    const institutionSpans = container.querySelectorAll('.institution-item');

    authorSpans.forEach(authorSpan => {
        const affiliations = authorSpan.dataset.affiliations.split(',').filter(n => n);
        
        authorSpan.addEventListener('mouseenter', () => {
            affiliations.forEach(affNum => {
                institutionSpans.forEach(instSpan => {
                    if (instSpan.dataset.affiliation === affNum) {
                        instSpan.classList.add('highlight');
                    }
                });
            });
        });

        authorSpan.addEventListener('mouseleave', () => {
            institutionSpans.forEach(instSpan => {
                instSpan.classList.remove('highlight');
            });
        });
    });

    institutionSpans.forEach(instSpan => {
        const affNum = instSpan.dataset.affiliation;

        instSpan.addEventListener('mouseenter', () => {
            authorSpans.forEach(authorSpan => {
                const affiliations = authorSpan.dataset.affiliations.split(',').filter(n => n);
                if (affiliations.includes(affNum)) {
                    authorSpan.classList.add('highlight');
                }
            });
        });

        instSpan.addEventListener('mouseleave', () => {
            authorSpans.forEach(authorSpan => {
                authorSpan.classList.remove('highlight');
            });
        });
    });

    // Add click event listeners to search by author/institution
    authorSpans.forEach(authorSpan => {
        authorSpan.addEventListener('click', () => {
            const authorInput = document.getElementById('author');
            if (authorInput) {
                authorInput.value = authorSpan.dataset.name;
                authorInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    });

    institutionSpans.forEach(instSpan => {
        instSpan.addEventListener('click', () => {
            const institutionInput = document.getElementById('institution');
            if (institutionInput) {
                institutionInput.value = instSpan.dataset.name;
                institutionInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    });

    return container;
}

function createReleasesSection(releases, searchParams = {}) {
    const sortedReleases = sortReleasesByDate(releases);

    const releaseItems = sortedReleases.map(release => {
        const { date, venueName, status } = formatRelease(release);
        const isMatch = matchesSearch(venueName, searchParams.venue);
        const venueSpan = html`<span class="release-venue clickable-venue${isMatch ? ' search-match' : ''}" data-venue="${venueName ?? ''}">${venueName ?? 'Unknown'}</span>`;
        
        // Extract year from date and make it clickable
        let dateElement;
        if (date && date.length >= 4) {
            const year = date.substring(0, 4);
            const rest = date.substring(4);
            dateElement = html`<strong class="release-date"><span class="clickable-year" data-year="${year}">${year}</span>${rest}</strong>`;
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

    const container = html`
        <div class="paper-meta-item">
            <div class="paper-releases">${releaseItems}</div>
        </div>
    `;

    // Add click event listeners to search by venue
    const venueSpans = container.querySelectorAll('.clickable-venue');
    venueSpans.forEach(venueSpan => {
        venueSpan.addEventListener('click', () => {
            const venueInput = document.getElementById('venue');
            if (venueInput && venueSpan.dataset.venue) {
                venueInput.value = venueSpan.dataset.venue;
                venueInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    });

    // Add click event listeners to search by year
    const yearSpans = container.querySelectorAll('.clickable-year');
    yearSpans.forEach(yearSpan => {
        yearSpan.addEventListener('click', () => {
            const year = yearSpan.dataset.year;
            const startDateInput = document.getElementById('start_date');
            const endDateInput = document.getElementById('end_date');
            if (startDateInput && endDateInput && year) {
                startDateInput.value = `${year}-01-01`;
                endDateInput.value = `${year}-12-31`;
                startDateInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    });

    return container;
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
    const abstractHtml = html`<div class="paper-abstract">${paper.abstract}</div>`
    const topicsHtml = html`<div class="paper-topics">${paper.topics.map(topic =>
        html`<span class="badge topic">${topic.name ?? topic.display_name ?? 'Unknown'}</span>`
    )}</div>`
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

function createValidationButtons(paper) {
    const container = html`
        <div class="validation-buttons">
            <button class="btn-yes">Yes</button>
            <button class="btn-no">No</button>
            <button class="btn-unknown">Unknown</button>
            <span class="status-message"></span>
        </div>
    `;

    const buttons = container.querySelectorAll('button');
    const statusMessage = container.querySelector('.status-message');
    const yesBtn = buttons[0];
    const noBtn = buttons[1];
    const unknownBtn = buttons[2];

    const paperId = paper.id;

    function updateButtonStyles(isValid, isInvalid) {
        // Reset all buttons to grey
        yesBtn.style.backgroundColor = '#6c757d';
        noBtn.style.backgroundColor = '#6c757d';
        unknownBtn.style.backgroundColor = '#6c757d';
        yesBtn.style.color = 'white';
        noBtn.style.color = 'white';
        unknownBtn.style.color = 'white';
        yesBtn.style.border = 'none';
        noBtn.style.border = 'none';
        unknownBtn.style.border = 'none';

        // Color the button that matches current state
        if (isValid) {
            yesBtn.style.backgroundColor = '#28a745';
        } else if (isInvalid) {
            noBtn.style.backgroundColor = '#dc3545';
        } else {
            unknownBtn.style.backgroundColor = '#fd7e14';
        }
    }

    // Set initial button styles based on paper flags
    const flags = paper.flags ?? [];
    const isValid = flags.includes('valid');
    const isInvalid = flags.includes('invalid');
    updateButtonStyles(isValid, isInvalid);

    async function setFlagOnServer(flag, value) {
        const response = await fetch('/api/v1/set_flag', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                paper_id: paperId,
                flag: flag,
                value: value
            })
        });

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message);
        }
        return result;
    }

    async function handleValidation(action) {
        if (paperId === null) {
            statusMessage.textContent = 'Error: No paper ID available';
            return;
        }

        // Disable all buttons while processing
        buttons.forEach(btn => btn.disabled = true);
        statusMessage.textContent = 'Processing...';

        try {
            if (action === 'yes') {
                // Set valid, unset invalid
                await setFlagOnServer('valid', true);
                await setFlagOnServer('invalid', false);
                updateButtonStyles(true, false);
                statusMessage.textContent = 'Marked as valid';
            } else if (action === 'no') {
                // Set invalid, unset valid
                await setFlagOnServer('invalid', true);
                await setFlagOnServer('valid', false);
                updateButtonStyles(false, true);
                statusMessage.textContent = 'Marked as invalid';
            } else if (action === 'unknown') {
                // Unset both
                await setFlagOnServer('valid', false);
                await setFlagOnServer('invalid', false);
                updateButtonStyles(false, false);
                statusMessage.textContent = 'Validation cleared';
            }
            statusMessage.style.color = '#28a745';
        } catch (error) {
            statusMessage.textContent = `Error: ${error.message}`;
            statusMessage.style.color = '#dc3545';
        } finally {
            // Re-enable buttons
            buttons.forEach(btn => btn.disabled = false);
        }
    }

    yesBtn.onclick = () => handleValidation('yes');
    noBtn.onclick = () => handleValidation('no');
    unknownBtn.onclick = () => handleValidation('unknown');

    return container;
}

function createEditIcon(paper) {
    const editIcon = html`
        <a href="/edit/${paper.id}" target="_blank" class="edit-icon" style="
            display: inline-flex;
            align-items: center;
            margin-left: 8px;
            color: #6c757d;
            text-decoration: none;
            transition: color 0.2s;
        " title="Edit paper">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="
                width: 16px;
                height: 16px;
            ">
                <path d="M11.4001 18.1612L11.4001 18.1612L18.796 10.7653C17.7894 10.3464 16.5972 9.6582 15.4697 8.53068C14.342 7.40298 13.6537 6.21058 13.2348 5.2039L5.83882 12.5999L5.83879 12.5999C5.26166 13.1771 4.97307 13.4657 4.7249 13.7838C4.43213 14.1592 4.18114 14.5653 3.97634 14.995C3.80273 15.3593 3.67368 15.7465 3.41556 16.5208L2.05445 20.6042C1.92743 20.9852 2.0266 21.4053 2.31063 21.6894C2.59466 21.9734 3.01478 22.0726 3.39584 21.9456L7.47918 20.5844C8.25351 20.3263 8.6407 20.1973 9.00498 20.0237C9.43469 19.8189 9.84082 19.5679 10.2162 19.2751C10.5343 19.0269 10.823 18.7383 11.4001 18.1612Z" fill="currentColor"/>
                <path d="M20.8482 8.71306C22.3839 7.17735 22.3839 4.68748 20.8482 3.15178C19.3125 1.61607 16.8226 1.61607 15.2869 3.15178L14.3999 4.03882C14.4121 4.0755 14.4246 4.11268 14.4377 4.15035C14.7628 5.0875 15.3763 6.31601 16.5303 7.47002C17.6843 8.62403 18.9128 9.23749 19.85 9.56262C19.8875 9.57563 19.9245 9.58817 19.961 9.60026L20.8482 8.71306Z" fill="currentColor"/>
            </svg>
        </a>
    `;
    
    // Add hover effect
    editIcon.addEventListener('mouseenter', () => {
        editIcon.style.color = '#2c5aa0';
    });
    editIcon.addEventListener('mouseleave', () => {
        editIcon.style.color = '#6c757d';
    });
    
    return editIcon;
}

function createPaperElement(paper, searchParams = {}) {
    const validationButtons = showValidationButtons ? createValidationButtons(paper) : null;
    const editIcon = isValidator ? createEditIcon(paper) : null;

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
            ${editIcon}
        </h3>
    `;

    return html`
        <li class="paper-item">
            ${titleWithEdit}
            ${createAuthorsSection(paper.authors, searchParams)}
            ${createReleasesSection(paper.releases, searchParams)}
            ${createDetailsSection(paper)}
            ${validationButtons}
        </li>
    `;
}

function createPagination(offset, count, total, nextOffset, showTotalFound = false) {
    const start = offset + 1;
    const end = offset + count;
    const paperWord = total !== 1 ? 'papers' : 'paper';

    const prevButton = html`<button disabled="${offset === 0}">Previous</button>`;
    prevButton.onclick = () => {
        const newOffset = Math.max(0, offset - PAGE_SIZE);
        performSearch(currentParams, newOffset);
    };

    const nextButton = html`<button disabled="${nextOffset === null}">Next</button>`;
    nextButton.onclick = () => {
        if (nextOffset !== null) {
            performSearch(currentParams, nextOffset);
        }
    };

    const totalFoundInfo = showTotalFound
        ? html`<div class="results-info"><span class="count">${total}</span> ${paperWord} found</div>`
        : html`<div></div>`;

    return html`
        <div class="pagination">
            ${totalFoundInfo}
            ${prevButton}
            <div class="page-info">Showing ${start}-${end} of ${total}</div>
            ${nextButton}
        </div>
    `;
}

function displayResults(data) {
    totalResults = data.total;

    const paperWord = data.total !== 1 ? 'papers' : 'paper';

    if (data.results.length === 0) {
        const noResults = html`
            <div class="no-results">
                No papers found. Try adjusting your search criteria.
            </div>
        `;
        setResults(noResults);
        return;
    }

    const paginationTop = createPagination(data.offset ?? currentOffset, data.count, data.total, data.next_offset, true);

    const paperElements = data.results.map(paper => createPaperElement(paper, currentParams));
    const paperList = html`<ul class="paper-list">${paperElements}</ul>`;

    const paginationBottom = data.total > PAGE_SIZE
        ? createPagination(data.offset ?? currentOffset, data.count, data.total, data.next_offset)
        : null;

    setResults(paginationTop, paperList, paginationBottom);
}

function displayLoading() {
    setResults(html`<div class="loading">Loading...</div>`);
}

function displayError(error) {
    setResults(html`<div class="error-message">Error loading results: ${error.message}</div>`);
}

function updateUrlParams(params, offset) {
    const urlParams = new URLSearchParams();
    
    if (params.title) urlParams.set('title', params.title);
    if (params.author) urlParams.set('author', params.author);
    if (params.institution) urlParams.set('institution', params.institution);
    if (params.venue) urlParams.set('venue', params.venue);
    if (params.start_date) urlParams.set('start_date', params.start_date);
    if (params.end_date) urlParams.set('end_date', params.end_date);
    if (params.validated) urlParams.set('validated', params.validated);
    if (offset > 0) urlParams.set('offset', offset.toString());

    const newUrl = urlParams.toString() 
        ? `${window.location.pathname}?${urlParams.toString()}`
        : window.location.pathname;
    
    window.history.replaceState({}, '', newUrl);
}

async function performSearch(params, offset = 0) {
    currentParams = params;
    currentOffset = offset;

    updateUrlParams(params, offset);
    displayLoading();

    try {
        const data = await fetchSearchResults(params, offset);
        displayResults(data);
    } catch (error) {
        console.error('Search failed:', error);
        displayError(error);
    }
}

const debouncedSearch = debounce((params) => {
    performSearch(params, 0);
}, 300);

export function searchPapers(hasValidateCapability = false, enableValidationButtons = false) {
    // Store the capability flags
    isValidator = hasValidateCapability;
    showValidationButtons = enableValidationButtons;

    const form = document.getElementById('searchForm');
    const titleInput = document.getElementById('title');
    const authorInput = document.getElementById('author');
    const institutionInput = document.getElementById('institution');
    const venueInput = document.getElementById('venue');
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    const validatedRadios = document.querySelectorAll('input[name="validated"]');

    function getValidatedValue() {
        const checked = document.querySelector('input[name="validated"]:checked');
        return checked ? checked.value : '';
    }

    function handleInputChange() {
        const params = {
            title: titleInput.value.trim(),
            author: authorInput.value.trim(),
            institution: institutionInput.value.trim(),
            venue: venueInput.value.trim(),
            start_date: startDateInput.value,
            end_date: endDateInput.value,
            validated: getValidatedValue()
        };

        // Always perform search, even with empty criteria
        debouncedSearch(params);
    }

    titleInput.addEventListener('input', handleInputChange);
    authorInput.addEventListener('input', handleInputChange);
    institutionInput.addEventListener('input', handleInputChange);
    venueInput.addEventListener('input', handleInputChange);
    startDateInput.addEventListener('input', handleInputChange);
    endDateInput.addEventListener('input', handleInputChange);
    validatedRadios.forEach(radio => {
        radio.addEventListener('change', handleInputChange);
    });

    // Prevent form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
    });

    // Clear search button
    const clearButton = document.getElementById('clearSearch');
    clearButton.addEventListener('click', () => {
        titleInput.value = '';
        authorInput.value = '';
        institutionInput.value = '';
        venueInput.value = '';
        startDateInput.value = '';
        endDateInput.value = '';
        // Reset validated radio to "All"
        const allRadio = document.querySelector('input[name="validated"][value=""]');
        if (allRadio) {
            allRadio.checked = true;
        }
        handleInputChange();
    });

    // Perform initial search if URL has parameters
    const urlParams = new URLSearchParams(window.location.search);
    const initialParams = {
        title: urlParams.get('title') || '',
        author: urlParams.get('author') || '',
        institution: urlParams.get('institution') || '',
        venue: urlParams.get('venue') || '',
        start_date: urlParams.get('start_date') || '',
        end_date: urlParams.get('end_date') || '',
        validated: urlParams.get('validated') || ''
    };
    const initialOffset = parseInt(urlParams.get('offset') || '0', 10);

    // Set form values from URL parameters
    titleInput.value = initialParams.title;
    authorInput.value = initialParams.author;
    institutionInput.value = initialParams.institution;
    venueInput.value = initialParams.venue;
    startDateInput.value = initialParams.start_date;
    endDateInput.value = initialParams.end_date;

    // Set the validated radio button
    if (initialParams.validated) {
        const radioToCheck = document.querySelector(`input[name="validated"][value="${initialParams.validated}"]`);
        if (radioToCheck) {
            radioToCheck.checked = true;
        }
    }

    // Always perform initial search, even with empty criteria
    performSearch(initialParams, initialOffset);
}
