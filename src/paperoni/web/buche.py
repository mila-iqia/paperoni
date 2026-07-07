"""Render discovered papers into a buche cell as HTML.

This reuses the exact same rendering code as the web backend
(``assets/paper.js`` + ``assets/common.js``): the papers are serialized to the
same JSON shape the REST API produces, handed to the browser, and turned into
DOM nodes by ``createPaperElement``. A dark-mode stylesheet (``discover.css``)
is layered on top of the web stylesheet (``style.css``).
"""

from pathlib import Path

from serieux import JSON

ASSETS = Path(__file__).parent / "assets"

_FILTER_SYSTEM_PROMPT = """\
You generate Python filter code for the paperoni paper browser.

The user describes which papers to KEEP. Write the BODY of `async def __operate(paper):` \
— no def line, just the indented body. If you need imports or helpers, put them before a \
line containing only `#####`.

The `paper` object has:
- paper.title: str
- paper.abstract: str | None
- paper.authors: list of PaperAuthor
  - .display_name: str
  - .author.name: str (canonical)
  - .affiliations: list[Institution]  — .name: str, .country: str | None
- paper.releases: list of Release
  - .venue.name: str, .venue.series: str
  - .venue.type: str  ('conference', 'journal', 'workshop', ...)
  - .venue.date: date object
- paper.topics: list[Topic]  — .name: str
- paper.links: list[Link]  — .type: str, .link: str
- paper.flags: set[str]

Return True to include, False to exclude.
Return ONLY raw Python, no markdown fences, no explanation.

Example — NeurIPS papers since 2020:
    from datetime import date
    #####
    for r in paper.releases:
        if 'neurips' in r.venue.series.lower() and r.venue.date >= date(2020, 1, 1):
            return True
    return False
"""


# JS that, once the paper.js module URL / data are on `window`, dynamically
# loads the module and builds one card per paper. It runs as a real module
# script (created via the DOM) so that `import` works inside buche's eval
# context. It also wires up arrow-key navigation, `q`/`Escape` to quit,
# `/` for live text search, and `%` to open a Python code-filter editor.
_RENDER_JS = """
(function () {
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

    // --- ES module: renders cards via createPaperElement, exposes window.DISCOVER_RENDER ---
    const mod = document.createElement('script');
    mod.type = 'module';
    mod.textContent = `
        import { createPaperElement } from '${window.DISCOVER_PAPER_JS}';

        const list = document.getElementById('paper-list');
        const items = window.DISCOVER_PAPERS || [];
        const scored = !!window.DISCOVER_SCORED;

        function renderCards(term) {
            list.innerHTML = '';
            let count = 0;
            for (let i = 0; i < items.length; i++) {
                const entry = items[i];
                const paper = (scored && entry && entry.value) ? entry.value : entry;
                if (term && !window._paperMatchesSearch(paper, term)) continue;
                const card = createPaperElement(paper);
                let item;
                if (scored && entry && typeof entry.score === 'number') {
                    item = document.createElement('li');
                    item.className = 'paper-item-with-score';
                    item.tabIndex = -1;
                    const band = document.createElement('div');
                    band.className = 'score-band';
                    band.textContent = Math.round(entry.score);
                    item.appendChild(band);
                    item.appendChild(card);
                } else {
                    item = card;
                    item.tabIndex = -1;
                }
                item.dataset.paperIndex = String(i);
                if (term) window._highlightInElement(item, term);
                list.appendChild(item);
                count++;
            }
            if (count === 0) {
                const empty = document.createElement('li');
                empty.className = 'discover-empty';
                empty.textContent = term ? ('No papers match "' + term + '"') : 'No papers discovered.';
                list.appendChild(empty);
            }
            return count;
        }

        window.DISCOVER_RENDER = renderCards;
        renderCards('');

        // Focus the first card so arrow navigation works immediately.
        const first = list.querySelector('[tabindex="-1"]');
        if (first) first.focus();
    `;
    document.head.appendChild(mod);

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
    const headerEl = document.querySelector('.discover-header');
    const originalHeader = headerEl ? headerEl.textContent : '';
    const totalCount = (window.DISCOVER_PAPERS || []).length;

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
        if (window.DISCOVER_RENDER) window.DISCOVER_RENDER('');
        if (headerEl) headerEl.textContent = originalHeader;
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
        if (!window.DISCOVER_RENDER) return;
        const count = window.DISCOVER_RENDER(term);
        if (headerEl) {
            headerEl.textContent = term
                ? (count + ' / ' + totalCount + ' paper' + (totalCount === 1 ? '' : 's'))
                : originalHeader;
        }
        const countEl = document.getElementById('search-count');
        if (countEl) countEl.textContent = term ? (count + ' / ' + totalCount) : '';
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
            const fmod = document.createElement('script');
            fmod.type = 'module';
            fmod.textContent = `
                import { basicSetup, EditorView } from 'https://esm.sh/codemirror';
                import { EditorState, Prec } from 'https://esm.sh/@codemirror/state';
                import { keymap } from 'https://esm.sh/@codemirror/view';
                import { indentWithTab } from 'https://esm.sh/@codemirror/commands';
                import { python } from 'https://esm.sh/@codemirror/lang-python';
                import { oneDark } from 'https://esm.sh/@codemirror/theme-one-dark';

                const runKeymap = Prec.highest(keymap.of([
                    { key: 'Ctrl-Enter', run: () => { window.runFilter().then(ok => ok && window.commitFilterEditor()); return true; } },
                    { key: 'Mod-Enter', run: () => { window.runFilter().then(ok => ok && window.commitFilterEditor()); return true; } },
                    { key: 'Escape', run: () => { window.closeFilterEditor(); return true; } },
                ]));

                const view = new EditorView({
                    state: EditorState.create({
                        doc: 'return True',
                        extensions: [basicSetup, oneDark, keymap.of([indentWithTab]), runKeymap, python()],
                    }),
                    parent: document.getElementById('filter-editor-host'),
                });

                window.FILTER_EDITOR = view;
                if (window._pendingFilterCode != null) {
                    const pending = window._pendingFilterCode;
                    window._pendingFilterCode = null;
                    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: pending } });
                }
                view.focus();
            `;
            document.head.appendChild(fmod);
        } else if (window.FILTER_EDITOR) {
            window.FILTER_EDITOR.focus();
        }
    }

    function closeFilterEditor() {
        hideBackdrop();
        filterPanel.setAttribute('hidden', '');
        const term = window._currentSearchTerm || '';
        if (window.DISCOVER_RENDER) {
            const c = window.DISCOVER_RENDER(term);
            if (headerEl) headerEl.textContent = term
                ? (c + ' / ' + totalCount + ' paper' + (totalCount === 1 ? '' : 's'))
                : originalHeader;
        }
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
                if (window.DISCOVER_RENDER) window.DISCOVER_RENDER(window._currentSearchTerm || '');
                const items = [...list.querySelectorAll(':scope > [tabindex="-1"]')];
                items.forEach(item => {
                    const idx = parseInt(item.dataset.paperIndex, 10);
                    item.style.display = (isNaN(idx) || indexSet.has(idx)) ? '' : 'none';
                });
                const vis = result.indices.length;
                if (statusEl) { statusEl.textContent = vis + ' / ' + totalCount + ' papers match'; statusEl.className = 'filter-status filter-ok'; }
                if (headerEl) headerEl.textContent = vis + ' / ' + totalCount + ' papers (code filter)';
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
})();
"""


async def render_papers(papers, paper_objects, scored=False):
    """Render a list of serialized papers into the buche main cell.

    `papers` is the JSON-serializable form of the papers (or of `Scored`
    wrappers when `scored` is True), matching the shape consumed by paper.js.
    `paper_objects` is the corresponding list of original Paper instances used
    by the Python code-filter callback (avoids re-deserializing the JSON).
    Runs an async event loop so Python callbacks (code filter, quit) work.
    """
    import os

    from buchelib import main_cell

    from ..operations import from_code

    cell = main_cell()
    bridge = cell.bridge
    body = cell.body()

    paper_js = ASSETS / "paper.js"
    common_js = ASSETS / "common.js"

    # Serve both modules under a single nonce so paper.js's relative
    # `import './common.js'` resolves correctly.
    bridge.avail(paper_js, common_js)
    paper_js_url = bridge.url(paper_js)

    count = len(papers)
    header = f"Discovered {count} paper{'' if count == 1 else 's'}"

    body.print(t'<link rel="stylesheet" href={ASSETS / "style.css"}>')
    body.print(t'<link rel="stylesheet" href={ASSETS / "discover.css"}>')

    body.print(t"""
        <div id="modal-backdrop" hidden></div>
        <div id="discover-root">
            <div class="discover-header">{header}</div>
            <div id="search-bar" class="discover-search-bar" hidden>
                <span class="search-icon">&#128269;</span>
                <input id="search-input" type="text" placeholder="Filter papers…" autocomplete="off" spellcheck="false" />
                <span id="search-count" class="search-count"></span>
                <button class="search-close" onclick="window.closeSearch()">&#10005;</button>
            </div>
            <div id="ai-prompt-bar" class="discover-ai-bar" hidden>
                <span class="ai-icon">&#10024;</span>
                <input id="ai-prompt-input" type="text" placeholder="Describe a filter (AI-generated)…" autocomplete="off" spellcheck="false" />
                <span id="ai-prompt-status" class="ai-prompt-status"></span>
                <button class="search-close" onclick="window.closeAiPrompt()">&#10005;</button>
            </div>
            <div id="filter-panel" class="discover-filter-panel" hidden>
                <div class="filter-panel-header">
                    <span class="filter-panel-title">Python filter &nbsp;<code>async def f(paper):</code></span>
                    <div class="filter-panel-actions">
                        <button id="filter-run" class="filter-btn">&#9654; Run <kbd>Ctrl+Enter</kbd></button>
                        <button class="filter-btn filter-btn-secondary" onclick="window.closeFilterEditor()">&#10005; Clear</button>
                    </div>
                </div>
                <div id="filter-editor-host"></div>
                <div id="filter-status" class="filter-status"></div>
            </div>
            <ul id="paper-list" class="paper-list" tabindex="0"></ul>
            <div class="discover-help" hidden>↑↓/jk navigate · / text search · % code filter · ! AI filter · Esc close panel · ? toggle help · q quit</div>
        </div>
    """)

    # --- Python callbacks ---

    async def run_filter(code: str) -> JSON:
        try:
            func = from_code(code)
        except Exception as e:
            return {"indices": None, "error": str(e)}
        indices = []
        for i, paper in enumerate(paper_objects):
            try:
                result = await func(paper)
                if result.changed:
                    indices.append(i)
            except Exception:
                pass
        return {"indices": indices, "error": None}

    async def generate_filter(prompt: str) -> JSON:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _FILTER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            code = response.choices[0].message.content.strip()
            if code.startswith("```"):
                lines = code.splitlines()
                end = next(
                    (
                        i
                        for i in range(len(lines) - 1, 0, -1)
                        if lines[i].startswith("```")
                    ),
                    len(lines),
                )
                code = "\n".join(lines[1:end])
            return {"code": code, "error": None}
        except Exception as e:
            return {"code": None, "error": str(e)}

    async def quit():
        os._exit(0)

    # Expose the data and module URL, then run the render/navigation script.
    body.exec(t"window.DISCOVER_PAPERS = {papers};")
    body.exec(t"window.DISCOVER_SCORED = {scored};")
    body.exec(t"window.DISCOVER_PAPER_JS = {paper_js_url};")
    body.exec(t"window._runFilterFn = {run_filter:js};")
    body.exec(t"window._generateFilterFn = {generate_filter:js};")
    body.exec(t"window._quitFn = {quit:js};")
    body.exec(t"window._currentSearchTerm = '';")
    body.exec(_RENDER_JS)

    # Keep the cell focused and visible after the process exits.
    cell.configure(sticky=True)

    # Process callbacks (code filter, quit) until the process is killed.
    async for obj in cell.inputs():
        if hasattr(obj, "call"):
            await obj.call()
