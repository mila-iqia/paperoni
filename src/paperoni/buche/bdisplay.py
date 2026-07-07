"""Render discovered papers into a buche cell as HTML.

This reuses the exact same rendering code as the web backend
(``assets/paper.js`` + ``assets/common.js``): the papers are serialized to the
same JSON shape the REST API produces, handed to the browser, and turned into
DOM nodes by ``createPaperElement``. A dark-mode stylesheet (``bpapers.css``)
is layered on top of the web stylesheet (``style.css``).
"""

from dataclasses import dataclass
from pathlib import Path

from hypetext.h import html
from serieux import JSON, serialize

ASSETS = Path(__file__).parent.parent / "web" / "assets"
B_ASSETS = Path(__file__).parent / "assets"


@dataclass
class PaperEntry:
    """A single serialized paper (or ``Scored`` wrapper) streamed to the browser.

    ``index`` is the paper's position in the stream, which matches its index in
    the Python-side ``paper_objects`` list used by the code filter. ``entry`` is
    the already-serialized JSON shape consumed by ``paper.js``.
    """

    index: int
    entry: JSON


@dataclass
class StreamComplete:
    """Sent once the source iterator is exhausted, to stop the spinner.

    ``total`` is the number of papers that were streamed.
    """

    total: int


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


async def render_papers(things, typ=None, scored=False):
    """Stream papers into the buche main cell, rendering them live.

    `things` is an async iterable of items to display (`Paper`, `Scored`
    wrappers, or `PaperDiff`); it is consumed lazily and each item is serialized
    and pushed to the browser on the fly through `cell.data()` as its source
    yields it, so the list grows in place instead of being dumped in one shot.
    `typ` is the serieux type used to serialize each item
    (inferred from the first item when None). `scored` indicates the items are
    `Scored` wrappers whose `.value` is the underlying paper.

    The original paper objects are accumulated as they stream so the Python
    code-filter callback can operate on them directly (by index) without
    re-deserializing the JSON. Runs an async event loop so Python callbacks
    (code filter, quit) work.
    """
    import os

    from buchelib import main_cell

    from ..operations import from_code

    cell = main_cell()
    bridge = cell.bridge
    body = cell.body()

    paper_js = ASSETS / "paper.js"
    common_js = ASSETS / "common.js"

    # Serve the modules under a single nonce so their relative imports (e.g.
    # paper.js's `import './common.js'`, workset.js's diff renderer) resolve.
    bridge.avail(
        paper_js,
        common_js,
        ASSETS / "workset.js",
        ASSETS / "translate.js",
        B_ASSETS / "bpapers.js",
        B_ASSETS / "filter-editor.js",
    )
    bpaper_js_url = bridge.url(B_ASSETS / "bpapers.js")

    body.print(t'<link rel="stylesheet" href={ASSETS / "style.css"}>')
    body.print(t'<link rel="stylesheet" href={B_ASSETS / "bpapers.css"}>')
    body.print(t"{(B_ASSETS / 'template.html').read_text():raw}")

    # Show the processing spinner right away, before the module even loads.
    body["#discover-header"].set(t'<span class="discover-spinner"></span>')

    # Populated incrementally as papers stream in; the code filter indexes into
    # this list, and by the time a filter can run (a user keypress) the stream
    # has already completed.
    paper_objects = []

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

    # Register the handler that renders each streamed paper. bpapers.js may not
    # have finished loading when the first entries arrive, so buffer them until
    # the module signals readiness and flushes the queue itself.
    cell.register_data_handlers(
        {
            PaperEntry: """(msg) => {
                if (window._DISCOVER_READY) {
                    window.DISCOVER_ADD(msg.entry, msg.index);
                } else {
                    (window._paperQueue = window._paperQueue || []).push([msg.entry, msg.index]);
                }
            }""",
            StreamComplete: """(msg) => {
                if (window._DISCOVER_READY) {
                    window.DISCOVER_DONE();
                } else {
                    window._streamDonePending = true;
                }
            }""",
        }
    )

    # Expose callbacks, then run the render/navigation script. The kind of each
    # streamed entry (plain paper, `Scored` wrapper, or diff) is inferred from
    # its shape in the browser, so no rendering mode needs to be sent here.
    body.exec(t"window._runFilterFn = {run_filter:js};")
    body.exec(t"window._generateFilterFn = {generate_filter:js};")
    body.exec(t"window._quitFn = {quit:js};")
    body.exec(t"window._currentSearchTerm = '';")

    s = str(html(t'<script type="module" src="{bpaper_js_url}"></script>'))
    body.print(t"{s:raw}")

    # Stream the papers one by one, updating the list live. The items are pulled
    # lazily from the `things` async generator as its source yields them; each is
    # serialized on its own and both accumulated (for the code filter) and pushed
    # to the browser.
    element_typ = typ
    i = 0
    async for thing in things:
        if element_typ is None:
            element_typ = type(thing)
        # Keep the underlying paper for the code filter: unwrap `Scored` and,
        # for diffs, prefer the incoming (`new`) paper over the existing one.
        if scored:
            obj = thing.value
        elif hasattr(thing, "new") or hasattr(thing, "current"):
            obj = getattr(thing, "new", None) or getattr(thing, "current", None)
        else:
            obj = thing
        paper_objects.append(obj)
        cell.data(PaperEntry(index=i, entry=serialize(element_typ, thing)))
        i += 1

    # The source is exhausted: stop the spinner and freeze the final count.
    cell.data(StreamComplete(total=i))

    # Keep the cell focused and visible after the process exits.
    cell.configure(sticky=True)

    # Process callbacks (code filter, quit) until the process is killed.
    async for obj in cell.inputs():
        if hasattr(obj, "call"):
            await obj.call()
