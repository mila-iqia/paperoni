from pathlib import Path

import markdown
from hrepr import H
from starbear import simplebear, template

from .common import template

here = Path(__file__).parent


@simplebear
async def __app__(request):
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
