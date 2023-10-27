from pathlib import Path

import markdown
from hrepr import H
from starbear import simplebear, template

from .common import template
from .utils import redirect_request_if_scraping

here = Path(__file__).parent


@simplebear
@redirect_request_if_scraping
async def help(request):
    """Help."""
    md = (here / "help.md").read_text()
    content = markdown.markdown(
        md, extensions=["markdown.extensions.attr_list"]
    )
    return template(
        here / "mila-template.html",
        title="Help",
        body=H.raw(content),
    )


ROUTES = help
