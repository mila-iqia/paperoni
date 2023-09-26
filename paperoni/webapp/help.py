from pathlib import Path

from starbear import simplebear, template

from .common import template

here = Path(__file__).parent


@simplebear
async def help(request):
    """Help."""
    return template(
        here / "mila-template.html",
        title="Help",
        body=template(
            here / "help.html",
        ),
    )


ROUTES = help
