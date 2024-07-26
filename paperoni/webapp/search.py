from pathlib import Path

from hrepr import H
from starbear import Queue

from ..config import papconf
from .common import SearchGUI, mila_template
from .render import paper_html

here = Path(__file__).parent


@mila_template(help="/help#search")
async def app(page, box):
    """Search for papers."""
    q = Queue()
    area = H.div["area"](id=True)

    with papconf.database as db:
        gui = SearchGUI(
            page,
            db,
            q,
            dict(page.query_params),
            defaults={"validation": "validated", "limit": 100},
        )
        box.print(gui)
        box.print(area)

        async for result in gui.loop(reset=box[area].clear):
            div = paper_html(result)
            box[area].print(div)


ROUTES = app
