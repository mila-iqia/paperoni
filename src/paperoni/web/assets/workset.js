import { html, join } from './common.js';
import {
    attachAuthorAffiliationHover,
    createAuthorsSection,
    createDetailsSection,
    createEditIcon,
    createReleasesSection,
    extractDomain,
    formatRelease,
    getScoreClass,
} from './paper.js';

function getAffName(aff) {
    return aff?.display_name || aff?.name || '';
}

/**
 * Simple word-level diff. Returns array of { type: 'equal'|'added'|'removed', value: string }.
 * Old = removed (red), new = added (green).
 */
function diffWords(text1, text2) {
    const words1 = (text1 || '').split(/\s+/).filter(Boolean);
    const words2 = (text2 || '').split(/\s+/).filter(Boolean);
    const result = [];
    let i = 0, j = 0;

    function lcsLength(a, b) {
        const m = a.length, n = b.length;
        const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                dp[i][j] = a[i - 1] === b[j - 1]
                    ? dp[i - 1][j - 1] + 1
                    : Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
        return dp;
    }

    function backtrack(a, b, dp, i, j) {
        if (i === 0 && j === 0) return [];
        if (i === 0) return backtrack(a, b, dp, 0, j - 1).concat({ type: 'added', value: b[j - 1] });
        if (j === 0) return backtrack(a, b, dp, i - 1, 0).concat({ type: 'removed', value: a[i - 1] });
        if (a[i - 1] === b[j - 1]) {
            return backtrack(a, b, dp, i - 1, j - 1).concat({ type: 'equal', value: a[i - 1] });
        }
        if (dp[i - 1][j] >= dp[i][j - 1]) {
            return backtrack(a, b, dp, i - 1, j).concat({ type: 'removed', value: a[i - 1] });
        }
        return backtrack(a, b, dp, i, j - 1).concat({ type: 'added', value: b[j - 1] });
    }

    const dp = lcsLength(words1, words2);
    return backtrack(words1, words2, dp, words1.length, words2.length);
}

/**
 * Sequence diff by key. Returns { type: 'equal'|'added'|'removed', value1?, value2?, idx1?, idx2? }.
 * For equal: value1 from arr1, value2 from arr2. For added: value from arr2. For removed: value from arr1.
 */
function diffSequence(arr1, arr2, keyFn = (x) => x) {
    const a = arr1 || [];
    const b = arr2 || [];
    const m = a.length;
    const n = b.length;

    const dp = Array(m + 1)
        .fill(null)
        .map(() => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] =
                keyFn(a[i - 1]) === keyFn(b[j - 1])
                    ? dp[i - 1][j - 1] + 1
                    : Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
    }

    const result = [];
    let i = m;
    let j = n;
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && keyFn(a[i - 1]) === keyFn(b[j - 1])) {
            result.unshift({ type: 'equal', value1: a[i - 1], value2: b[j - 1], idx1: i - 1, idx2: j - 1 });
            i--;
            j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            result.unshift({ type: 'added', value: b[j - 1], idx2: j - 1 });
            j--;
        } else {
            result.unshift({ type: 'removed', value: a[i - 1], idx1: i - 1 });
            i--;
        }
    }
    return result;
}

/**
 * Compare two values for equality (shallow, for list items).
 */
function valueKey(val) {
    if (val == null) return 'null';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
}

/**
 * Create a paper element showing diff between paperOld (baseline) and paperNew (updated).
 * Green = added (in new only), red = removed (in old only).
 * Exported for use by pending.js.
 */
export function createWorksetPaperDiffElement(paperOld, paperNew) {
    const info1 = paperOld?.info || {};
    const info2 = paperNew?.info || {};

    const firstLink = paperNew?.links?.[0] || paperOld?.links?.[0];
    const titleUrl = firstLink?.link ?? null;
    const firstPdfLink = paperNew?.links?.find(l => l.type?.toLowerCase().includes('pdf'))
        || paperOld?.links?.find(l => l.type?.toLowerCase().includes('pdf'));
    const pdfBadge = firstPdfLink
        ? html`<a href="${firstPdfLink.link}" target="_blank" class="badge pdf" title="${firstPdfLink.link}">PDF</a>`
        : null;

    // Title diff
    const title1 = paperOld?.title ?? '';
    const title2 = paperNew?.title ?? '';
    const titleSegments = diffWords(title1, title2);
    const titleSpans = titleSegments.map(seg => {
        if (seg.type === 'equal') return html`<span>${seg.value} </span>`;
        if (seg.type === 'added') return html`<span class="diff-added">${seg.value} </span>`;
        return html`<span class="diff-removed">${seg.value} </span>`;
    });
    const titleContent = titleUrl
        ? html`<a href="${titleUrl}" target="_blank" class="paper-title-link">${titleSpans}</a>`
        : html`<span>${titleSpans}</span>`;

    const titleWithEdit = html`
        <h3 class="paper-title" style="display: flex; align-items: center;">
            ${titleContent}
            ${pdfBadge}
        </h3>
    `;

    // Authors + affiliations diff - match by exact display_name
    const authorsOld = paperOld?.authors || [];
    const authorsNew = paperNew?.authors || [];

    // Build unified institution map: name -> { num, inOld, inNew }
    const instMap = new Map();
    let instNum = 1;
    for (const author of [...authorsOld, ...authorsNew]) {
        for (const aff of author.affiliations || []) {
            const name = getAffName(aff);
            if (name && !instMap.has(name)) {
                instMap.set(name, { num: instNum++, inOld: false, inNew: false });
            }
        }
    }
    for (const author of authorsOld) {
        for (const aff of author.affiliations || []) {
            const e = instMap.get(getAffName(aff));
            if (e) e.inOld = true;
        }
    }
    for (const author of authorsNew) {
        for (const aff of author.affiliations || []) {
            const e = instMap.get(getAffName(aff));
            if (e) e.inNew = true;
        }
    }

    function getAuthorAffNums(author) {
        return (author?.affiliations || [])
            .map(aff => instMap.get(getAffName(aff))?.num)
            .filter(n => n !== undefined)
            .sort((a, b) => a - b);
    }

    const authorItems = [];
    const authorKey = (a) => a?.display_name ?? 'Unknown';
    let segments = diffSequence(authorsOld, authorsNew, authorKey);

    // Merge removed+added for SAME author (same display_name) into "moved" so both swapped authors get arrows.
    // For renames (different names), keep BOTH removed and added so both old and new names show.
    const removedQueue = [];
    const output = [];
    for (const seg of segments) {
        if (seg.type === 'removed') {
            removedQueue.push({ seg, key: authorKey(seg.value) });
        } else if (seg.type === 'added') {
            const key = authorKey(seg.value);
            const idx = removedQueue.findIndex((r) => r.key === key);
            if (idx >= 0) {
                while (removedQueue.length > 0 && removedQueue[0].key !== key) {
                    output.push(removedQueue.shift().seg);
                }
                const { seg: rem } = removedQueue.shift();
                output.push({
                    type: 'moved',
                    value1: rem.value,
                    value2: seg.value,
                    idx1: rem.idx1,
                    idx2: seg.idx2,
                });
            } else {
                while (removedQueue.length > 0) {
                    output.push(removedQueue.shift().seg);
                }
                output.push(seg);
            }
        } else {
            while (removedQueue.length > 0) {
                output.push(removedQueue.shift().seg);
            }
            output.push(seg);
        }
    }
    while (removedQueue.length > 0) {
        output.push(removedQueue.shift().seg);
    }
    segments = output;

    for (const seg of segments) {
        if (seg.type === 'equal' || seg.type === 'moved') {
            const author1 = seg.value1 ?? seg.value2;
            const author2 = seg.value2 ?? seg.value1;
            const name = authorKey(author2);
            const affNums1 = new Set(getAuthorAffNums(author1));
            const affNums2 = new Set(getAuthorAffNums(author2));
            const allNums = [...new Set([...affNums1, ...affNums2])].sort((a, b) => a - b);
            const supParts = allNums
                .flatMap((n, i) => {
                    const in1 = affNums1.has(n);
                    const in2 = affNums2.has(n);
                    const cls = in1 && in2 ? '' : in2 ? 'diff-added' : 'diff-removed';
                    return [i > 0 ? ',' : null, html`<span class="${cls}">${n}</span>`];
                })
                .filter(Boolean);
            authorItems.push(
                html`<span class="author-name" data-affiliations="${allNums.join(',')}">${name}${supParts.length ? html`<sup>${supParts}</sup>` : ''}</span>`
            );
        } else if (seg.type === 'added') {
            const author = seg.value;
            const name = authorKey(author);
            const affNums = getAuthorAffNums(author);
            const supParts = affNums
                .flatMap((n, i) => {
                    const e = [...instMap.entries()].find(([, v]) => v.num === n);
                    const cls = e && e[1].inOld ? '' : 'diff-added';
                    return [i > 0 ? ',' : null, html`<span class="${cls}">${n}</span>`];
                })
                .filter(Boolean);
            authorItems.push(
                html`<span class="author-name diff-added" data-affiliations="${affNums.join(',')}">${name}${supParts.length ? html`<sup>${supParts}</sup>` : ''}</span>`
            );
        } else {
            const author = seg.value;
            const name = authorKey(author);
            const affNums = getAuthorAffNums(author);
            const supParts = affNums
                .flatMap((n, i) => {
                    const e = [...instMap.entries()].find(([, v]) => v.num === n);
                    const cls = e && e[1].inNew ? '' : 'diff-removed';
                    return [i > 0 ? ',' : null, html`<span class="${cls}">${n}</span>`];
                })
                .filter(Boolean);
            authorItems.push(
                html`<span class="author-name diff-removed" data-affiliations="${affNums.join(',')}">${name}${supParts.length ? html`<sup>${supParts}</sup>` : ''}</span>`
            );
        }
    }

    // Institutions list below authors - green/red by V1/V2
    const institutions = [...instMap.entries()].sort((a, b) => a[1].num - b[1].num);
    const instElements = institutions.map(([instName, { num, inOld, inNew }]) => {
        const cls = inOld && inNew ? '' : inNew ? 'diff-added' : 'diff-removed';
        return html`<span class="institution-item ${cls}" data-affiliation="${num}"><sup>${num}</sup>${instName}</span>`;
    });

    const authorsHtml = authorItems.length > 0
        ? html`
            <div class="paper-authors-container">
                <div class="paper-authors">${join(', ', authorItems)}</div>
                ${instElements.length ? html`<div class="paper-institutions">${join('; ', instElements)}</div>` : null}
            </div>
        `
        : html`<div class="paper-authors-container"><div class="paper-authors">No authors</div></div>`;

    attachAuthorAffiliationHover(authorsHtml);

    // Releases diff - match by key with consumption (handles duplicate venues)
    const releases1 = paperOld?.releases || [];
    const releases2 = paperNew?.releases || [];
    const releaseKey = (r) => `${r.venue?.name ?? ''}|${r.venue?.date ?? ''}|${r.peer_review_status ?? ''}`;
    const r2Counts = new Map();
    for (const r of releases2) {
        const k = releaseKey(r);
        r2Counts.set(k, (r2Counts.get(k) || 0) + 1);
    }
    const r1Counts = new Map();
    for (const r of releases1) {
        const k = releaseKey(r);
        r1Counts.set(k, (r1Counts.get(k) || 0) + 1);
    }
    const releaseItems = [];
    for (const r of releases1) {
        const key = releaseKey(r);
        const count = r2Counts.get(key) || 0;
        const in2 = count > 0;
        if (in2) r2Counts.set(key, count - 1);
        const cls = in2 ? '' : 'diff-removed';
        const { date, venueName, status } = formatRelease(r);
        const dateEl = html`<strong class="release-date">${date ?? '????-??-??'}</strong>`;
        const statusSpan = status ? html`<span class="release-status">${status}</span>` : null;
        releaseItems.push(html`
            <div class="release-item ${cls}">
                ${dateEl}
                ${statusSpan}
                <span class="release-venue">${venueName ?? 'Unknown'}</span>
            </div>
        `);
    }
    for (const r of releases2) {
        const key = releaseKey(r);
        const count = r1Counts.get(key) || 0;
        if (count > 0) {
            r1Counts.set(key, count - 1);
            continue;
        }
        const { date, venueName, status } = formatRelease(r);
        const dateEl = html`<strong class="release-date">${date ?? '????-??-??'}</strong>`;
        const statusSpan = status ? html`<span class="release-status">${status}</span>` : null;
        releaseItems.push(html`
            <div class="release-item diff-added">
                ${dateEl}
                ${statusSpan}
                <span class="release-venue">${venueName ?? 'Unknown'}</span>
            </div>
        `);
    }
    const releasesHtml = html`<div class="paper-meta-item"><div class="paper-releases">${releaseItems.length ? releaseItems : html`<div class="release-item">No releases</div>`}</div></div>`;

    // Abstract diff
    const abs1 = paperOld?.abstract ?? '';
    const abs2 = paperNew?.abstract ?? '';
    let abstractHtml = null;
    if (abs1 || abs2) {
        const absSegments = diffWords(abs1, abs2);
        const absSpans = absSegments.map(seg => {
            if (seg.type === 'equal') return html`<span>${seg.value} </span>`;
            if (seg.type === 'added') return html`<span class="diff-added">${seg.value} </span>`;
            return html`<span class="diff-removed">${seg.value} </span>`;
        });
        abstractHtml = html`<div class="paper-abstract-section"><div class="paper-abstract expanded">${absSpans}</div></div>`;
    }

    // Topics diff - exact match (order doesn't matter)
    const topicKey = t => t.name ?? t.display_name ?? '';
    const topics1 = (paperOld?.topics || []).map(topicKey).filter(Boolean);
    const topics2 = (paperNew?.topics || []).map(topicKey).filter(Boolean);
    const t1Set = new Set(topics1);
    const t2Set = new Set(topics2);
    const topicBadges = [];
    for (const t of topics1) {
        const cls = t2Set.has(t) ? '' : 'diff-removed';
        topicBadges.push(html`<span class="badge topic ${cls}">${t}</span>`);
    }
    for (const t of topics2) {
        if (t1Set.has(t)) continue;
        topicBadges.push(html`<span class="badge topic diff-added">${t}</span>`);
    }
    const topicsHtml = topicBadges.length
        ? html`<div class="paper-topics">${topicBadges}</div>`
        : null;

    // Links diff - exact match by type+url (order doesn't matter)
    const linkKey = (link) => `${link.type ?? ''}|${link.link ?? ''}`;
    const links1 = (paperOld?.links || []).map(linkKey);
    const links2 = (paperNew?.links || []).map(linkKey);
    const l1Set = new Set(links1);
    const l2Set = new Set(links2);
    const linkBadges = [];
    for (const link of paperOld?.links || []) {
        const key = linkKey(link);
        const cls = l2Set.has(key) ? '' : 'diff-removed';
        const linkType = link.type ?? 'unknown';
        const linkUrl = link.link ?? '';
        const domain = extractDomain(linkUrl);
        const typeContainsDomain = domain && linkType.toLowerCase().includes(domain.toLowerCase());
        const badgeText = (domain && !typeContainsDomain) ? `${linkType} (${domain})` : linkType;
        linkBadges.push(html`<a href="${linkUrl}" target="_blank" class="badge link ${cls}" title="${linkUrl}">${badgeText}</a>`);
    }
    for (const link of paperNew?.links || []) {
        const key = linkKey(link);
        if (l1Set.has(key)) continue;
        const linkType = link.type ?? 'unknown';
        const linkUrl = link.link ?? '';
        const domain = extractDomain(linkUrl);
        const typeContainsDomain = domain && linkType.toLowerCase().includes(domain.toLowerCase());
        const badgeText = (domain && !typeContainsDomain) ? `${linkType} (${domain})` : linkType;
        linkBadges.push(html`<a href="${linkUrl}" target="_blank" class="badge link diff-added" title="${linkUrl}">${badgeText}</a>`);
    }
    const linksContainer = linkBadges.length
        ? html`<div class="paper-links">${linkBadges}</div>`
        : null;

    // Info table diff (exclude comments - shown separately in pending)
    const allInfoKeys = new Set([...Object.keys(info1), ...Object.keys(info2)]);
    allInfoKeys.delete('comments');
    const infoRows = [];
    for (const key of allInfoKeys) {
        const v1 = info1[key];
        const v2 = info2[key];
        const v1Str = v1 != null ? (typeof v1 === 'object' ? JSON.stringify(v1) : String(v1)) : '';
        const v2Str = v2 != null ? (typeof v2 === 'object' ? JSON.stringify(v2) : String(v2)) : '';
        let valueContent;
        if (v1Str === v2Str) {
            valueContent = (v2Str || v1Str || 'null');
        } else {
            const segs = diffWords(v1Str, v2Str);
            valueContent = segs.map(seg => {
                if (seg.type === 'equal') return html`<span>${seg.value} </span>`;
                if (seg.type === 'added') return html`<span class="diff-added">${seg.value} </span>`;
                return html`<span class="diff-removed">${seg.value} </span>`;
            });
        }
        const in1 = key in info1;
        const in2 = key in info2;
        const rowCls = in1 && in2 ? '' : in2 ? 'diff-added' : 'diff-removed';
        infoRows.push(html`<tr class="${rowCls}"><td class="info-key">${key}</td><td class="info-value">${valueContent}</td></tr>`);
    }
    const infoTable = infoRows.length
        ? html`<table class="info-table"><tbody>${infoRows}</tbody></table>`
        : null;

    const detailsParts = [abstractHtml, topicsHtml, linksContainer].filter(Boolean);
    const detailsSection = detailsParts.length
        ? html`<div class="paper-details-section">${detailsParts}</div>`
        : null;

    // <div class="diff-legend">
    //     <span class="diff-legend-item"><span class="diff-swatch diff-removed"></span> In old only</span>
    //     <span class="diff-legend-item"><span class="diff-swatch diff-added"></span> In new only</span>
    //     <span class="diff-legend-hint">Shift+click tab to exit</span>
    // </div>

    return html`
        <div class="paper-content diff-view">
            ${titleWithEdit}
            ${authorsHtml}
            ${releasesHtml}
            ${detailsSection}
            ${infoTable}
        </div>
    `;
}

/**
 * Create diff view with three tabs: Diff (default), Old, New.
 * Exported for use by pending.js.
 */
export function createDiffViewWithTabs(paperOld, paperNew) {
    const diffContent = createWorksetPaperDiffElement(paperOld, paperNew);
    const excludeComments = { excludeFromInfo: ['comments'] };
    const oldContent = createWorksetPaperElement(paperOld, excludeComments);
    const newContent = createWorksetPaperElement(paperNew, excludeComments);

    const tabButtons = html`
        <div class="diff-tab-buttons">
            <button class="diff-tab diff-tab-diff active" data-diff-tab="diff">Diff</button>
            <button class="diff-tab diff-tab-old" data-diff-tab="old">Old</button>
            <button class="diff-tab diff-tab-new" data-diff-tab="new">New</button>
        </div>
    `;

    const tabContents = html`
        <div class="diff-tab-contents">
            <div class="tab-content active" data-diff-tab="diff">${diffContent}</div>
            <div class="tab-content" data-diff-tab="old">${oldContent}</div>
            <div class="tab-content" data-diff-tab="new">${newContent}</div>
        </div>
    `;

    const container = html`
        <div class="diff-view-with-tabs">
            <div class="workset-tabs diff-view-tabs-wrapper">
                ${tabContents}
                ${tabButtons}
            </div>
        </div>
    `;

    const buttons = container.querySelectorAll('.diff-tab[data-diff-tab]');
    const contents = container.querySelectorAll('.tab-content[data-diff-tab]');

    buttons.forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.diffTab;
            buttons.forEach(b => b.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            container.querySelector(`.tab-content[data-diff-tab="${tab}"]`).classList.add('active');
        });
    });

    return container;
}

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

function createInfoTable(info, excludeKeys = []) {
    if (!info || Object.keys(info).length === 0) {
        return null;
    }

    const excludeSet = new Set(excludeKeys);
    const rows = Object.entries(info)
        .filter(([key]) => !excludeSet.has(key))
        .map(([key, value]) => {
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

/** Exported for use by pending.js. Options: { excludeFromInfo: ['comments'], editSuggest: bool } */
export function createWorksetPaperElement(paper, options = {}) {
    const info = paper.info || {};
    const excludeFromInfo = options.excludeFromInfo || [];
    const editSuggest = options.editSuggest ?? false;

    // Get the first link URL if available
    const firstLink = paper.links && paper.links.length > 0 ? paper.links[0] : null;
    const titleUrl = firstLink ? firstLink.link : null;

    // Get the first PDF link if available
    const firstPdfLink = paper.links?.find(link => link.type?.toLowerCase().includes('pdf'));
    const pdfBadge = firstPdfLink
        ? html`<a href="${firstPdfLink.link}" target="_blank" class="badge pdf" title="${firstPdfLink.link}">PDF</a>`
        : null;

    const editIcon = editSuggest ? createEditIcon(paper, { suggest: true }) : null;

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

    const infoTable = createInfoTable(info, excludeFromInfo);

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
        
        // Exit diff mode if active (keyboard nav or programmatic switch)
        if (diffMode) {
            diffMode = false;
            diffV1Index = -1;
            diffV2Index = -1;
            buttons.forEach(btn => btn.classList.remove('diff-v1', 'diff-v2'));
            const diffContainer = worksetItem.querySelector('.tab-contents .diff-content-container');
            if (diffContainer) diffContainer.remove();
        }
        
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
    
    // Track if we're in diff mode (showing diff between two tabs)
    let diffMode = false;
    let diffV1Index = -1;
    let diffV2Index = -1;

    function showDiffView(v1Index, v2Index) {
        diffMode = true;
        diffV1Index = v1Index;
        diffV2Index = v2Index;
        const paperOld = allPapers[v2Index].paper;
        const paperNew = allPapers[v1Index].paper;

        // Hide all tab contents and show diff in a special container
        contents.forEach(c => c.classList.remove('active'));
        buttons.forEach(btn => btn.classList.remove('active'));
        buttons[v1Index].classList.add('diff-v1');
        buttons[v2Index].classList.add('diff-v2');

        // Create or update diff content container
        let diffContainer = worksetItem.querySelector('.tab-contents .diff-content-container');
        if (!diffContainer) {
            diffContainer = document.createElement('div');
            diffContainer.className = 'diff-content-container tab-content active';
            worksetItem.querySelector('.tab-contents').appendChild(diffContainer);
        }
        diffContainer.innerHTML = '';
        diffContainer.appendChild(createDiffViewWithTabs(paperOld, paperNew));
        diffContainer.classList.add('active');
    }

    function exitDiffView(restoreToIndex) {
        if (!diffMode) return;
        diffMode = false;
        diffV1Index = -1;
        diffV2Index = -1;
        buttons.forEach(btn => {
            btn.classList.remove('diff-v1', 'diff-v2');
        });
        const diffContainer = worksetItem.querySelector('.tab-contents .diff-content-container');
        if (diffContainer) diffContainer.remove();
        switchToTab(restoreToIndex !== undefined ? restoreToIndex : currentTabIndex);
    }

    buttons.forEach((button, idx) => {
        button.addEventListener('click', (e) => {
            if (e.shiftKey) {
                if (diffMode) {
                    exitDiffView(); // Restore to V1 (currentTabIndex)
                } else {
                    // paperOld = clicked tab, paperNew = currently selected
                    const v1Index = currentTabIndex;
                    const v2Index = idx;
                    if (v1Index !== v2Index) {
                        showDiffView(v1Index, v2Index);
                    }
                }
                setFocused(true);
            } else {
                if (diffMode) {
                    exitDiffView(idx); // Switch to clicked tab
                } else {
                    switchToTab(idx);
                }
                setFocused(true);
            }
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
