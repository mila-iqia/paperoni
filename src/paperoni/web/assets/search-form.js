/**
 * Shared search form utilities. Used by search and operate pages.
 */

/**
 * Get search parameters from the form elements (by ID).
 * @returns {Object} { title, author, institution, venue, status, start_date, end_date }
 */
export function getSearchParams() {
    const titleEl = document.getElementById('title');
    const authorEl = document.getElementById('author');
    const institutionEl = document.getElementById('institution');
    const venueEl = document.getElementById('venue');
    const statusEl = document.getElementById('status');
    const startDateEl = document.getElementById('start_date');
    const endDateEl = document.getElementById('end_date');

    return {
        title: titleEl?.value?.trim() ?? '',
        author: authorEl?.value?.trim() ?? '',
        institution: institutionEl?.value?.trim() ?? '',
        venue: venueEl?.value?.trim() ?? '',
        // Comma-separated release types; "-xyz" entries exclude that status.
        status: (statusEl?.value ?? '')
            .split(',')
            .map((s) => s.trim())
            .filter((s) => s),
        start_date: startDateEl?.value ?? '',
        end_date: endDateEl?.value ?? '',
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
    if (params.status) {
        for (const s of params.status) queryParams.append('status', s);
    }
    if (params.start_date) queryParams.append('start_date', params.start_date);
    if (params.end_date) queryParams.append('end_date', params.end_date);
}

/**
 * Convert search params to flags list (for POST body).
 * @param {Object} params - From getSearchParams()
 * @returns {string[]} List of flag strings
 */
export function searchParamsToFlags(params) {
    return [];
}

/**
 * Wire the "Peer reviewed" checkbox as a shortcut for the Type field: checking
 * it adds "peer-reviewed" to the comma-separated statuses, unchecking removes
 * it. The checkbox also stays in sync when the Type field is edited directly.
 * @param {Function} [triggerSearch] - Called after the checkbox edits the field.
 */
export function setupPeerReviewedShortcut(triggerSearch) {
    const checkbox = document.getElementById('peerReviewed');
    const statusEl = document.getElementById('status');
    if (!checkbox || !statusEl) return;

    const TOKEN = 'peer-reviewed';
    const tokens = () =>
        statusEl.value.split(',').map((s) => s.trim()).filter((s) => s);

    checkbox.addEventListener('change', () => {
        let ts = tokens();
        const has = ts.includes(TOKEN);
        if (checkbox.checked && !has) {
            ts.push(TOKEN);
        } else if (!checkbox.checked && has) {
            ts = ts.filter((t) => t !== TOKEN);
        }
        statusEl.value = ts.join(', ');
        triggerSearch?.();
    });

    // Keep the checkbox reflecting manual edits to the Type field.
    statusEl.addEventListener('input', () => {
        checkbox.checked = tokens().includes(TOKEN);
    });
}

/**
 * Set the "Peer reviewed" checkbox to reflect the current Type field contents.
 * Use after programmatically populating the form (e.g. restoring from the URL).
 */
export function syncPeerReviewedCheckbox() {
    const checkbox = document.getElementById('peerReviewed');
    const statusEl = document.getElementById('status');
    if (!checkbox || !statusEl) return;
    checkbox.checked = statusEl.value
        .split(',')
        .map((s) => s.trim())
        .includes('peer-reviewed');
}

/**
 * Clear the search form fields.
 */
export function clearSearchForm() {
    const titleEl = document.getElementById('title');
    const authorEl = document.getElementById('author');
    const institutionEl = document.getElementById('institution');
    const venueEl = document.getElementById('venue');
    const statusEl = document.getElementById('status');
    const startDateEl = document.getElementById('start_date');
    const endDateEl = document.getElementById('end_date');
    const peerReviewedEl = document.getElementById('peerReviewed');

    if (titleEl) titleEl.value = '';
    if (authorEl) authorEl.value = '';
    if (institutionEl) institutionEl.value = '';
    if (venueEl) venueEl.value = '';
    if (statusEl) statusEl.value = '';
    if (startDateEl) startDateEl.value = '';
    if (endDateEl) endDateEl.value = '';
    if (peerReviewedEl) peerReviewedEl.checked = false;
}
