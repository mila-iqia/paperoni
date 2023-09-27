"""Simple search app.
Run with `uvicorn apps.search:app`
"""

from pathlib import Path

from hrepr import H
from starbear import Queue, bear

from .common import SearchGUI, config, mila_template
from .render import paper_html

here = Path(__file__).parent


@bear
@mila_template(help="/help#search")
async def app(page, box):
    """Search for papers."""
    q = Queue()
    area = H.div["area"]().autoid()

    with config().database as db:
        gui = SearchGUI(page, db, q, dict(page.query_params), defaults={})
        box.print(gui)
        box.print(area)

        async for result in gui.loop(reset=box[area].clear):
            div = paper_html(result)
            box[area].print(div)


ROUTES = app
