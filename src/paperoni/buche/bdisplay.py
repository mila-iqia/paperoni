"""Render discovered papers into a buche cell as HTML.

This reuses the exact same rendering code as the web backend
(``assets/paper.js`` + ``assets/common.js``): the papers are serialized to the
same JSON shape the REST API produces, handed to the browser, and turned into
DOM nodes by ``createPaperElement``. A dark-mode stylesheet (``bpapers.css``)
is layered on top of the web stylesheet (``style.css``).
"""

from pathlib import Path

from serieux import JSON

ASSETS = Path(__file__).parent.parent / "web" / "assets"
B_ASSETS = Path(__file__).parent / "assets"

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
_RENDER_JS = (B_ASSETS / "bpapers.js").read_text()


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

    body.print(t'<link rel="stylesheet" href={ASSETS / "style.css"}>')
    body.print(t'<link rel="stylesheet" href={B_ASSETS / "bpapers.css"}>')
    body.print(t"{(B_ASSETS / 'template.html').read_text():raw}")

    count = len(papers)
    header = f"Discovered {count} paper{'' if count == 1 else 's'}"
    body["#discover-header"].set(header)

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
