"""Simple search app.
Run with `uvicorn apps.search:app`
"""

import os
from pathlib import Path

from hrepr import H
from starbear import Queue, bear

from ..config import load_config
from .common import SearchGUI, mila_template
from .render import paper_html

here = Path(__file__).parent


@bear
@mila_template
async def app(page, box):
    """Search for papers."""
    q = Queue()
    area = H.div["area"]().autoid()

    page["#title"].print(
        "Search for papers",
        H.a["ball"]("?", href="/help#search"),
    )

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            gui = SearchGUI(page, db, q, dict(page.query_params), defaults={})
            box.print(gui)
            box.print(area)

            async for result in gui.loop(reset=box[area].clear):
                div = paper_html(result)
                box[area].print(div)


ROUTES = app
