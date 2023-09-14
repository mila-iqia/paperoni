"""Simple search app.
Run with `uvicorn apps.search:app`
"""

import os
from pathlib import Path

from hrepr import H
from starbear import Queue, bear

from ..config import load_config
from .common import SearchGUI
from .render import paper_html

here = Path(__file__).parent


@bear
async def app(page):
    """Search for papers."""
    q = Queue()
    page["head"].print(H.link(rel="stylesheet", href=here / "app-style.css"))
    area = H.div["area"]().autoid()

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            gui = SearchGUI(page, db, q, dict(page.query_params), defaults={})
            page.print(gui)
            page.print(area)

            async for result in gui.loop(reset=page[area].clear):
                div = paper_html(result)
                page[area].print(div)


ROUTES = app
