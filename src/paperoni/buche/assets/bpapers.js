import { createPaperElement } from '../../web/assets/paper.js';
import { createWorksetPaperDiffElement } from '../../web/assets/workset.js';

export function run() {

    const root = document.getElementById('discover-root');
    const list = document.getElementById('paper-list');

    // Size the scroll region to the iframe (see buchelib sizing guidance).
    const info = window.bucheInfo || {};
    if (info.dynamicHeight === false) {
        root.style.height = '100vh';
    } else if (info.maxHeight) {
        root.style.height = (info.maxHeight - 4) + 'px';
    } else {
        root.style.height = '520px';
    }

    // --- Search helpers (exposed on window so the ES module can call them) ---

    window._paperMatchesSearch = function(paper, term) {
        if (!term) return true;
        const t = term.toLowerCase();
        function has(s) { return (s || '').toLowerCase().includes(t); }
        if (has(paper.title)) return true;
        if (has(paper.abstract)) return true;
        if (paper.authors) {
            for (const a of paper.authors) {
                if (has(a.display_name)) return true;
                for (const aff of (a.affiliations || [])) {
                    if (has(aff.display_name || aff.name)) return true;
                }
            }
        }
        if (paper.releases) {
            for (const r of paper.releases) {
                if (r.venue && has(r.venue.name)) return true;
            }
        }
        if (paper.topics) {
            for (const topic of paper.topics) {
                if (has(topic.name || topic.display_name)) return true;
            }
        }
        if (paper.links) {
            for (const link of paper.links) {
                if (has(link.type)) return true;
            }
        }
        return false;
    };

    window._highlightInElement = function(el, term) {
        if (!term) return;
        const lowerTerm = term.toLowerCase();
        const len = term.length;
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
        const nodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.textContent.toLowerCase().includes(lowerTerm)) nodes.push(node);
        }
        for (const textNode of nodes) {
            const parent = textNode.parentNode;
            if (!parent) continue;
            const tag = parent.tagName;
            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') continue;
            const text = textNode.textContent;
            const lower = text.toLowerCase();
            const frag = document.createDocumentFragment();
            let i = 0;
            while (i < text.length) {
                const pos = lower.indexOf(lowerTerm, i);
                if (pos === -1) { frag.appendChild(document.createTextNode(text.slice(i))); break; }
                if (pos > i) frag.appendChild(document.createTextNode(text.slice(i, pos)));
                const mark = document.createElement('mark');
                mark.className = 'search-highlight';
                mark.textContent = text.slice(pos, pos + len);
                frag.appendChild(mark);
                i = pos + len;
            }
            parent.replaceChild(frag, textNode);
        }
    };

    // --- ES module: renders cards streamed live, one entry at a time ---
    //
    // Entries are pushed one at a time from Python through cell.data(); each
    // call lands in window.DISCOVER_ADD. `items` grows as they arrive (indexed
    // by the entry's position in the Python-side paper_objects list, so the
    // code filter stays in sync). renderCards() rebuilds the list from scratch
    // (used by search); addPaper() appends a single card without touching the
    // rest.
    //
    // The kind of each entry is inferred from its shape:
    //   - `Scored` wrapper .......... has a `value` field (+ a `score`)
    //   - paper diff ................ has a `current` and/or `new` field
    //   - plain paper ............... anything else
    // A bare Paper carries its own `score` field, so the score band is shown
    // only for wrappers and diffs, never for a plain paper.

    const items = [];        // items[index] = serialized entry (may be sparse)
    const headerEl = document.querySelector('.discover-header');
    let streamDone = false;  // set once the Python source is exhausted

    function isDiff(o) { return !!o && ('current' in o || 'new' in o); }

    // Unwrap a `Scored` wrapper to the thing it scores.
    function payloadOf(entry) {
        return (entry && 'value' in entry) ? entry.value : entry;
    }

    // The representative paper used for search / highlight (new side of a diff).
    function paperOf(entry) {
        const p = payloadOf(entry);
        return isDiff(p) ? (p.new || p.current || {}) : p;
    }

    // Score to show on the band, or null for a bare paper (which is not a
    // wrapper/diff even though it may have its own `score` field).
    function scoreOf(entry) {
        const isWrapperOrDiff = entry && ('value' in entry || isDiff(entry));
        return (isWrapperOrDiff && typeof entry.score === 'number') ? entry.score : null;
    }

    // Build the card element for an entry's payload (paper or diff).
    function cardOf(entry) {
        const p = payloadOf(entry);
        return isDiff(p)
            ? createWorksetPaperDiffElement(p.current, p.new)
            : createPaperElement(p);
    }

    function totalCount() {
        let n = 0;
        for (let i = 0; i < items.length; i++) if (items[i] !== undefined) n++;
        return n;
    }

    function visibleCount() {
        return list.querySelectorAll(':scope > [tabindex="-1"]').length;
    }

    function anyPanelOpen() {
        // Queried lazily (not via the consts below) because addPaper may run
        // during the init flush, before those declarations are reached.
        const sb = document.getElementById('search-bar');
        const ab = document.getElementById('ai-prompt-bar');
        const fp = document.getElementById('filter-panel');
        return (sb && !sb.hasAttribute('hidden'))
            || (ab && !ab.hasAttribute('hidden'))
            || (fp && !fp.hasAttribute('hidden'));
    }

    function updateHeader(term) {
        if (!headerEl) return;
        const total = totalCount();
        const plural = total === 1 ? '' : 's';
        headerEl.textContent = '';
        // While the source is still streaming (and no search is active), show a
        // spinner alongside the live count instead of a final "Discovered" tally.
        if (!term && !streamDone) {
            const spinner = document.createElement('span');
            spinner.className = 'discover-spinner';
            headerEl.appendChild(spinner);
        }
        const label = document.createElement('span');
        label.textContent = term
            ? (visibleCount() + ' / ' + total + ' paper' + plural)
            : (total + ' paper' + plural);
        headerEl.appendChild(label);
    }

    // Called (via the StreamComplete data handler) when the source iterator is
    // exhausted: stop the spinner and settle on the final count.
    window.DISCOVER_DONE = function() {
        streamDone = true;
        if (totalCount() === 0) showEmpty(window._currentSearchTerm || '');
        updateHeader(window._currentSearchTerm || '');
    };

    function clearEmpty() {
        const empty = list.querySelector('.discover-empty');
        if (empty) empty.remove();
    }

    function showEmpty(term) {
        clearEmpty();
        const empty = document.createElement('li');
        empty.className = 'discover-empty';
        empty.textContent = term ? ('No papers match "' + term + '"') : 'No papers discovered.';
        list.appendChild(empty);
    }

    function makeItemElement(entry, index) {
        const card = cardOf(entry);
        const score = scoreOf(entry);
        let item;
        if (score !== null) {
            item = document.createElement('li');
            item.className = 'paper-item-with-score';
            item.tabIndex = -1;
            const band = document.createElement('div');
            band.className = 'score-band';
            band.textContent = Math.round(score);
            item.appendChild(band);
            item.appendChild(card);
        } else {
            item = card;
            item.tabIndex = -1;
        }
        item.dataset.paperIndex = String(index);
        return item;
    }

    // Append one entry's card to the list if it matches `term`; returns whether
    // it was shown.
    function appendCard(entry, index, term) {
        if (term && !window._paperMatchesSearch(paperOf(entry), term)) return false;
        const item = makeItemElement(entry, index);
        if (term) window._highlightInElement(item, term);
        list.appendChild(item);
        return true;
    }

    // Full rebuild from `items` — used by search / filter reset.
    function renderCards(term) {
        list.innerHTML = '';
        let count = 0;
        for (let i = 0; i < items.length; i++) {
            if (items[i] === undefined) continue;
            if (appendCard(items[i], i, term)) count++;
        }
        if (count === 0) showEmpty(term);
        return count;
    }

    // Live append of a single streamed paper.
    function addPaper(entry, index) {
        items[index] = entry;
        clearEmpty();
        const term = window._currentSearchTerm || '';
        const shown = appendCard(entry, index, term);
        updateHeader(term);
        const countEl = document.getElementById('search-count');
        if (countEl && term) countEl.textContent = visibleCount() + ' / ' + totalCount();
        // Focus the first card once one exists, unless the user is elsewhere.
        if (shown && !anyPanelOpen() && !list.contains(document.activeElement)) {
            const first = list.querySelector('[tabindex="-1"]');
            if (first && (document.activeElement === document.body
                          || document.activeElement === list
                          || document.activeElement === null)) {
                first.focus();
            }
        }
        return shown;
    }

    window.DISCOVER_RENDER = renderCards;
    window.DISCOVER_ADD = addPaper;

    // Drain anything that streamed in before this module finished loading, then
    // mark ready so later entries render immediately.
    const queued = window._paperQueue || [];
    window._paperQueue = [];
    window._DISCOVER_READY = true;
    for (const [entry, index] of queued) addPaper(entry, index);
    // The stream may have already completed before the module loaded.
    if (window._streamDonePending) streamDone = true;
    if (totalCount() === 0 && streamDone) showEmpty('');
    updateHeader(window._currentSearchTerm || '');

    // --- Modal backdrop ---
    const backdrop = document.getElementById('modal-backdrop');
    backdrop.addEventListener('click', function() {
        if (!searchBar.hasAttribute('hidden')) closeSearch();
        else if (!aiBar.hasAttribute('hidden')) closeAiPrompt();
        else if (!filterPanel.hasAttribute('hidden')) closeFilterEditor();
    });
    
    function showBackdrop() { backdrop.removeAttribute('hidden'); }
    function hideBackdrop() { backdrop.setAttribute('hidden', ''); }
    
    // --- Search bar open / close ---
    const searchBar = document.getElementById('search-bar');
    const searchInput = document.getElementById('search-input');

    function openSearch() {
        showBackdrop();
        searchBar.removeAttribute('hidden');
        searchInput.value = '';
        searchInput.focus();
    }

    function closeSearch() {
        hideBackdrop();
        searchBar.setAttribute('hidden', '');
        searchInput.value = '';
        window._currentSearchTerm = '';
        renderCards('');
        updateHeader('');
        const first = list.querySelector('[tabindex="-1"]');
        (first || list).focus();
    }

    function commitSearch() {
        hideBackdrop();
        searchBar.setAttribute('hidden', '');
        const first = list.querySelector('[tabindex="-1"]');
        (first || list).focus();
    }

    window.closeSearch = closeSearch;

    searchInput.addEventListener('input', function() {
        const term = searchInput.value;
        window._currentSearchTerm = term;
        const count = renderCards(term);
        updateHeader(term);
        const countEl = document.getElementById('search-count');
        if (countEl) countEl.textContent = term ? (count + ' / ' + totalCount()) : '';
    });

    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            e.preventDefault();
            closeSearch();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            commitSearch();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            const first = list.querySelector('[tabindex="-1"]');
            if (first) first.focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const cards = list.querySelectorAll('[tabindex="-1"]');
            if (cards.length) cards[cards.length - 1].focus();
        }
    });

    // --- Code filter panel ---
    const filterPanel = document.getElementById('filter-panel');
    let filterEditorLoaded = false;

    function openFilterEditor() {
        showBackdrop();
        filterPanel.removeAttribute('hidden');
        if (!filterEditorLoaded) {
            filterEditorLoaded = true;
            import("./filter-editor.js").then(mod => mod.install());
        } else if (window.FILTER_EDITOR) {
            window.FILTER_EDITOR.focus();
        }
    }

    function closeFilterEditor() {
        hideBackdrop();
        filterPanel.setAttribute('hidden', '');
        const term = window._currentSearchTerm || '';
        renderCards(term);
        updateHeader(term);
        const first = list.querySelector('[tabindex="-1"]');
        (first || list).focus();
    }

    function commitFilterEditor() {
        hideBackdrop();
        filterPanel.setAttribute('hidden', '');
        const first = [...list.querySelectorAll(':scope > [tabindex="-1"]')].find(el => el.style.display !== 'none');
        (first || list).focus();
    }

    window.closeFilterEditor = closeFilterEditor;
    window.commitFilterEditor = commitFilterEditor;

    window.setFilterCode = function(code) {
        if (window.FILTER_EDITOR) {
            const view = window.FILTER_EDITOR;
            view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: code } });
            showBackdrop();
            filterPanel.removeAttribute('hidden');
            view.focus();
        } else {
            window._pendingFilterCode = code;
            openFilterEditor();
        }
    };

    // --- AI prompt bar ---
    const aiBar = document.getElementById('ai-prompt-bar');
    const aiInput = document.getElementById('ai-prompt-input');
    const aiStatus = document.getElementById('ai-prompt-status');

    function openAiPrompt() {
        showBackdrop();
        aiBar.removeAttribute('hidden');
        aiInput.value = '';
        aiStatus.textContent = '';
        aiInput.removeAttribute('disabled');
        aiInput.focus();
    }

    function closeAiPrompt() {
        hideBackdrop();
        aiBar.setAttribute('hidden', '');
        const first = list.querySelector('[tabindex="-1"]');
        (first || list).focus();
    }

    window.closeAiPrompt = closeAiPrompt;

    async function submitAiPrompt() {
        const prompt = aiInput.value.trim();
        if (!prompt || !window._generateFilterFn) return;
        aiStatus.textContent = 'Generating…';
        aiInput.setAttribute('disabled', '');
        try {
            const result = await window._generateFilterFn(prompt);
            if (result.error) {
                aiStatus.textContent = result.error;
                aiInput.removeAttribute('disabled');
                aiInput.focus();
            } else {
                closeAiPrompt();
                window.setFilterCode(result.code);
            }
        } catch(err) {
            aiStatus.textContent = String(err);
            aiInput.removeAttribute('disabled');
            aiInput.focus();
        }
    }

    aiInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') { e.preventDefault(); closeAiPrompt(); }
        else if (e.key === 'Enter') { e.preventDefault(); submitAiPrompt(); }
    });

    window.runFilter = async function() {
        const editor = window.FILTER_EDITOR;
        if (!editor || !window._runFilterFn) return;
        const code = editor.state.doc.toString();
        const statusEl = document.getElementById('filter-status');
        if (statusEl) { statusEl.textContent = 'Running…'; statusEl.className = 'filter-status filter-running'; }
        try {
            const result = await window._runFilterFn(code);
            if (result.error) {
                if (statusEl) { statusEl.textContent = result.error; statusEl.className = 'filter-status filter-error'; }
                return false;
            } else {
                const indexSet = new Set(result.indices);
                renderCards(window._currentSearchTerm || '');
                const cardEls = [...list.querySelectorAll(':scope > [tabindex="-1"]')];
                cardEls.forEach(item => {
                    const idx = parseInt(item.dataset.paperIndex, 10);
                    item.style.display = (isNaN(idx) || indexSet.has(idx)) ? '' : 'none';
                });
                const total = totalCount();
                const vis = result.indices.length;
                if (statusEl) { statusEl.textContent = vis + ' / ' + total + ' papers match'; statusEl.className = 'filter-status filter-ok'; }
                if (headerEl) headerEl.textContent = vis + ' / ' + total + ' papers (code filter)';
                return true;
            }
        } catch(err) {
            if (statusEl) { statusEl.textContent = String(err); statusEl.className = 'filter-status filter-error'; }
            return false;
        }
    };

    document.getElementById('filter-run').addEventListener('click', () => window.runFilter());

    // --- Keyboard navigation over the cards ---
    list.addEventListener('keydown', function(e) {
        if (e.key === '/') {
            e.preventDefault();
            openSearch();
            return;
        }
        if (e.key === '%') {
            e.preventDefault();
            openFilterEditor();
            return;
        }
        if (e.key === '!') {
            e.preventDefault();
            openAiPrompt();
            return;
        }
        if (e.key === '?') {
            e.preventDefault();
            document.querySelector('.discover-help')?.toggleAttribute('hidden');
            return;
        }
        const cards = [...list.querySelectorAll(':scope > [tabindex="-1"]')];
        const idx = cards.indexOf(document.activeElement);
        if (e.key === 'ArrowDown' || e.key === 'j') {
            e.preventDefault();
            cards[Math.min(idx + 1, cards.length - 1)]?.focus();
        } else if (e.key === 'ArrowUp' || e.key === 'k') {
            e.preventDefault();
            cards[Math.max(idx - 1, 0)]?.focus();
        } else if (e.key === 'Home') {
            e.preventDefault();
            cards[0]?.focus();
        } else if (e.key === 'End') {
            e.preventDefault();
            cards[cards.length - 1]?.focus();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            if (!searchBar.hasAttribute('hidden')) {
                closeSearch();
            } else if (!aiBar.hasAttribute('hidden')) {
                closeAiPrompt();
            } else if (!filterPanel.hasAttribute('hidden')) {
                closeFilterEditor();
            } else {
                if (window.buche && window.buche.blur) window.buche.blur();
            }
        } else if (e.key === 'q') {
            e.preventDefault();
            if (window.buche && window.buche.blur) window.buche.blur();
            if (window._quitFn) window._quitFn();
        }
    });

    window.autofocus = () => {
        if (!searchBar.hasAttribute('hidden')) { searchInput.focus(); return; }
        if (!aiBar.hasAttribute('hidden')) { aiInput.focus(); return; }
        if (!filterPanel.hasAttribute('hidden') && window.FILTER_EDITOR) { window.FILTER_EDITOR.focus(); return; }
        (document.activeElement && list.contains(document.activeElement)
            ? document.activeElement
            : list.querySelector('[tabindex="-1"]') || list
        ).focus();
    };
}

run();
