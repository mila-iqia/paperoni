/**
 * Shared search form utilities. Used by search and operate pages.
 */

/**
 * Get search parameters from the form elements (by ID).
 * @returns {Object} { title, author, institution, venue, start_date, end_date, peerReviewed }
 */
export function getSearchParams() {
    const titleEl = document.getElementById('title');
    const authorEl = document.getElementById('author');
    const institutionEl = document.getElementById('institution');
    const venueEl = document.getElementById('venue');
    const startDateEl = document.getElementById('start_date');
    const endDateEl = document.getElementById('end_date');
    const peerReviewedEl = document.getElementById('peerReviewed');

    return {
        title: titleEl?.value?.trim() ?? '',
        author: authorEl?.value?.trim() ?? '',
        institution: institutionEl?.value?.trim() ?? '',
        venue: venueEl?.value?.trim() ?? '',
        start_date: startDateEl?.value ?? '',
        end_date: endDateEl?.value ?? '',
        peerReviewed: peerReviewedEl?.checked ?? false,
    };
}

/**
 * Append search parameters to a URLSearchParams object.
 * @param {Object} params - From getSearchParams()
 * @param {URLSearchParams} queryParams - Mutable URLSearchParams to append to
 */
export function appendSearchParamsTo(queryParams, params) {
    if (params.title) queryParams.append('title', params.title);
    if (params.author) queryParams.append('author', params.author);
    if (params.institution) queryParams.append('institution', params.institution);
    if (params.venue) queryParams.append('venue', params.venue);
    if (params.start_date) queryParams.append('start_date', params.start_date);
    if (params.end_date) queryParams.append('end_date', params.end_date);

    if (params.peerReviewed) {
        queryParams.append('flags', 'peer-reviewed');
    }
}

/**
 * Convert search params to flags list (for POST body).
 * @param {Object} params - From getSearchParams()
 * @returns {string[]} List of flag strings
 */
export function searchParamsToFlags(params) {
    const flags = [];
    if (params.peerReviewed) {
        flags.push('peer-reviewed');
    }
    return flags;
}

/**
 * Clear the search form fields.
 */
export function clearSearchForm() {
    const titleEl = document.getElementById('title');
    const authorEl = document.getElementById('author');
    const institutionEl = document.getElementById('institution');
    const venueEl = document.getElementById('venue');
    const startDateEl = document.getElementById('start_date');
    const endDateEl = document.getElementById('end_date');
    const peerReviewedEl = document.getElementById('peerReviewed');

    if (titleEl) titleEl.value = '';
    if (authorEl) authorEl.value = '';
    if (institutionEl) institutionEl.value = '';
    if (venueEl) venueEl.value = '';
    if (startDateEl) startDateEl.value = '';
    if (endDateEl) endDateEl.value = '';
    if (peerReviewedEl) peerReviewedEl.checked = false;
}
