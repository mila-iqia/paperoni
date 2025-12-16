"""
FastAPI route for searching papers with a web interface.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates

here = Path(__file__).parent


def install_search(app: FastAPI) -> FastAPI:
    """Install the search web interface route."""

    hascap = app.auth.get_email_capability
    templates = Jinja2Templates(directory=str((here / "templates").resolve()))

    @app.get("/search", dependencies=[Depends(hascap("search"))])
    async def search_page(request: Request):
        """Render the search page."""
        return templates.TemplateResponse("search.html", {"request": request})

    return app
