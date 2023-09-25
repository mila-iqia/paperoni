from pathlib import Path

from starbear import simplebear, template

here = Path(__file__).parent


@simplebear
async def help(request):
    return template(here / "help.html", _asset=lambda name: here / name)


ROUTES = help
