import { html, join } from './common.js';

export function formatAuthorsWithAffiliations(authors) {
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
            .filter(num => num !== undefined)
            .sort((a, b) => a - b);

        return { name, affNumbers };
    });

    return {
        authorData,
        institutions: Array.from(institutionMap.entries()).sort((a, b) => a[1] - b[1])
    };
}

export function formatDate(dateString, precision) {
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

export function formatRelease(release) {
    const date = release.venue?.date
        ? formatDate(release.venue.date, release.venue.date_precision)
        : null;
    const venueName = release.venue?.name ?? null;
    const status = release.peer_review_status ?? null;

    return { date, venueName, status };
}

// export function sortReleasesByDate(releases) {
//     return [...releases].sort((a, b) => {
//         // Parse dates manually to avoid timezone issues
//         const parseDate = (dateString) => {
//             if (!dateString) return new Date(0);
//             const parts = dateString.split('-');
//             if (parts.length === 3) {
//                 // Create date in local timezone to avoid UTC conversion
//                 return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
//             }
//             return new Date(dateString); // Fallback
//         };

//         const dateA = parseDate(a.venue?.date);
//         const dateB = parseDate(b.venue?.date);
//         return dateB - dateA; // Most recent first
//     });
// }

export function matchesSearch(text, searchTerm) {
    if (!searchTerm || !text) return false;
    return text.toLowerCase().includes(searchTerm.toLowerCase());
}

export function extractDomain(url) {
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

/**
 * Attaches hover listeners so that hovering an author highlights their affiliations
 * and vice versa. Works on any container with .author-name (data-affiliations="1,2,3")
 * and .institution-item (data-affiliation="1") elements.
 * @param {HTMLElement} container - Element containing author and institution spans
 */
export function attachAuthorAffiliationHover(container) {
    const authorSpans = container.querySelectorAll('.author-name');
    const institutionSpans = container.querySelectorAll('.institution-item');

    authorSpans.forEach(authorSpan => {
        const affiliations = (authorSpan.dataset.affiliations || '').split(',').filter(n => n);

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
            institutionSpans.forEach(instSpan => instSpan.classList.remove('highlight'));
        });
    });

    institutionSpans.forEach(instSpan => {
        const affNum = instSpan.dataset.affiliation;

        instSpan.addEventListener('mouseenter', () => {
            authorSpans.forEach(authorSpan => {
                const affiliations = (authorSpan.dataset.affiliations || '').split(',').filter(n => n);
                if (affiliations.includes(affNum)) {
                    authorSpan.classList.add('highlight');
                }
            });
        });

        instSpan.addEventListener('mouseleave', () => {
            authorSpans.forEach(authorSpan => authorSpan.classList.remove('highlight'));
        });
    });
}

/**
 * Creates the authors section with affiliations.
 * @param {Array} authors - List of author objects
 * @param {Object} options - Optional settings
 * @param {Object} options.searchParams - Search parameters for highlighting (author, institution)
 * @param {Function} options.onAuthorClick - Callback when author is clicked: (authorName) => void
 * @param {Function} options.onInstitutionClick - Callback when institution is clicked: (institutionName) => void
 * @returns {HTMLElement} The authors section element
 */
export function createAuthorsSection(authors, options = {}) {
    const { searchParams = {}, onAuthorClick = null, onInstitutionClick = null } = options;

    if (!authors || authors.length === 0) {
        return html`<div class="paper-authors-container"><div class="paper-authors">No authors</div></div>`;
    }

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

    attachAuthorAffiliationHover(container);

    // Add click event listeners if callbacks are provided
    const authorSpans = container.querySelectorAll('.author-name');
    const institutionSpans = container.querySelectorAll('.institution-item');
    if (onAuthorClick) {
        authorSpans.forEach(authorSpan => {
            authorSpan.addEventListener('click', () => {
                onAuthorClick(authorSpan.dataset.name);
            });
        });
    }

    if (onInstitutionClick) {
        institutionSpans.forEach(instSpan => {
            instSpan.addEventListener('click', () => {
                onInstitutionClick(instSpan.dataset.name);
            });
        });
    }

    return container;
}

/**
 * Creates the releases section for a paper.
 * @param {Array} releases - List of release objects
 * @param {Object} options - Optional settings
 * @param {Object} options.searchParams - Search parameters for highlighting (venue)
 * @param {Function} options.onVenueClick - Callback when venue is clicked: (venueName) => void
 * @param {Function} options.onYearClick - Callback when year is clicked: (year) => void
 * @returns {HTMLElement} The releases section element
 */
export function createReleasesSection(releases, options = {}) {
    const { searchParams = {}, onVenueClick = null, onYearClick = null } = options;

    if (!releases || releases.length === 0) {
        return html`<div class="paper-meta-item"><div class="paper-releases">No releases</div></div>`;
    }

    const sortedReleases = releases; //sortReleasesByDate(releases);

    const releaseItems = sortedReleases.map(release => {
        const { date, venueName, status } = formatRelease(release);
        const isMatch = matchesSearch(venueName, searchParams.venue);
        
        const venueClass = onVenueClick ? 'release-venue clickable-venue' : 'release-venue';
        const venueSpan = html`<span class="${venueClass}${isMatch ? ' search-match' : ''}" data-venue="${venueName ?? ''}">${venueName ?? 'Unknown'}</span>`;
        
        // Extract year from date and make it clickable if callback is provided
        let dateElement;
        if (date && date.length >= 4) {
            const year = date.substring(0, 4);
            const rest = date.substring(4);
            if (onYearClick) {
                dateElement = html`<strong class="release-date"><span class="clickable-year" data-year="${year}">${year}</span>${rest}</strong>`;
            } else {
                dateElement = html`<strong class="release-date">${year}${rest}</strong>`;
            }
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

    // Add click event listeners if callbacks are provided
    if (onVenueClick) {
        const venueSpans = container.querySelectorAll('.clickable-venue');
        venueSpans.forEach(venueSpan => {
            venueSpan.addEventListener('click', () => {
                if (venueSpan.dataset.venue) {
                    onVenueClick(venueSpan.dataset.venue);
                }
            });
        });
    }

    if (onYearClick) {
        const yearSpans = container.querySelectorAll('.clickable-year');
        yearSpans.forEach(yearSpan => {
            yearSpan.addEventListener('click', () => {
                if (yearSpan.dataset.year) {
                    onYearClick(yearSpan.dataset.year);
                }
            });
        });
    }

    return container;
}

export function createLinksSection(links) {
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

export function createAbstractSection(abstract) {
    if (!abstract) return null;

    const container = html`
        <div class="paper-abstract-section">
            <div class="paper-abstract collapsed">${abstract}</div>
        </div>
    `;

    const abstractDiv = container.querySelector('.paper-abstract');
    
    abstractDiv.addEventListener('click', () => {
        abstractDiv.classList.toggle('collapsed');
        abstractDiv.classList.toggle('expanded');
    });

    return container;
}

export function createTopicsSection(topics) {
    if (!topics || topics.length === 0) return null;

    const VISIBLE_COUNT = 5;
    const hasMore = topics.length > VISIBLE_COUNT;
    const visibleTopics = topics.slice(0, VISIBLE_COUNT);
    const hiddenTopics = topics.slice(VISIBLE_COUNT);

    const visibleBadges = visibleTopics.map(topic =>
        html`<span class="badge topic">${topic.name ?? topic.display_name ?? 'Unknown'}</span>`
    );

    const hiddenBadges = hiddenTopics.map(topic =>
        html`<span class="badge topic">${topic.name ?? topic.display_name ?? 'Unknown'}</span>`
    );

    const moreLink = hasMore
        ? html`<span class="topics-more-link">More (${hiddenTopics.length})</span>`
        : null;

    const hiddenContainer = hasMore
        ? html`<span class="topics-hidden">${hiddenBadges}</span>`
        : null;

    const container = html`
        <div class="paper-topics">
            ${visibleBadges}
            ${moreLink}
            ${hiddenContainer}
        </div>
    `;

    if (hasMore) {
        const moreLinkEl = container.querySelector('.topics-more-link');
        const hiddenContainerEl = container.querySelector('.topics-hidden');

        moreLinkEl.addEventListener('click', () => {
            hiddenContainerEl.classList.add('visible');
            moreLinkEl.style.display = 'none';
        });
    }

    return container;
}

export function createDetailsSection(paper) {
    const abstractHtml = createAbstractSection(paper.abstract);
    const topicsHtml = createTopicsSection(paper.topics);
    const linksHtml = createLinksSection(paper.links);

    return html`
        <div class="paper-details-section">
            ${abstractHtml}
            ${topicsHtml}
            ${linksHtml}
        </div>
    `;
}

/**
 * Gets the CSS class for a score value based on thresholds.
 * @param {number} score - The score value
 * @returns {string} The CSS class name
 */
export function getScoreClass(score) {
    if (score >= 20) return 'score-20';
    if (score >= 10) return 'score-10';
    if (score >= 5) return 'score-5';
    if (score >= 3) return 'score-3';
    if (score >= 2) return 'score-2';
    if (score >= 1) return 'score-1';
    return 'score-0';
}

/**
 * Creates a score band element for displaying paper scores.
 * @param {number} score - The score value
 * @returns {HTMLElement} The score band element
 */
export function createScoreBand(score) {
    const scoreClass = getScoreClass(score);
    return html`
        <div class="score-band ${scoreClass}">
            <div class="score-value">${Math.round(score)}</div>
        </div>
    `;
}

export function createEditIcon(paper, options = {}) {
    const suggest = options.suggest ?? false;
    const editUrl = paper.id != null ? `/edit/${paper.id}${suggest ? '?suggest=1' : ''}` : `/edit/new${suggest ? '?suggest=1' : ''}`;
    const editIcon = html`
        <a href="${editUrl}" target="_blank" class="edit-icon" style="
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

/**
 * Creates a paper element for display.
 * @param {Object} paper - The paper object
 * @param {Object} options - Optional settings
 * @param {Object} options.searchParams - Search parameters for highlighting
 * @param {Function} options.onAuthorClick - Callback when author is clicked: (authorName) => void
 * @param {Function} options.onInstitutionClick - Callback when institution is clicked: (institutionName) => void
 * @param {Function} options.onVenueClick - Callback when venue is clicked: (venueName) => void
 * @param {Function} options.onYearClick - Callback when year is clicked: (year) => void
 * @param {HTMLElement} options.bottomSection - Optional HTML element to display at the bottom of the paper item
 * @param {boolean} options.showEditIcon - Whether to show the edit icon
 * @returns {HTMLElement} The paper element
 */
export function createPaperElement(paper, options = {}) {
    const { 
        searchParams = {}, 
        onAuthorClick = null,
        onInstitutionClick = null,
        onVenueClick = null,
        onYearClick = null,
        bottomSection = null,
        showEditIcon = false 
    } = options;

    const editIcon = showEditIcon ? createEditIcon(paper) : null;

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
            ${createAuthorsSection(paper.authors, { searchParams, onAuthorClick, onInstitutionClick })}
            ${createReleasesSection(paper.releases, { searchParams, onVenueClick, onYearClick })}
            ${createDetailsSection(paper)}
            ${bottomSection}
        </li>
    `;
}
