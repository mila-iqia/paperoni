"""
FastAPI route for searching papers with a web interface.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from serieux import deserialize

here = Path(__file__).parent


def install_search(app: FastAPI) -> FastAPI:
    """Install the search web interface route."""

    hascap = app.auth.get_email_capability
    templates = Jinja2Templates(directory=str((here / "templates").resolve()))

    @app.get("/search")
    async def search_page(request: Request, user: str = Depends(hascap("search"))):
        """Render the search page."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        is_validator = app.auth.capabilities.check(user, validate)
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "is_validator": is_validator,
                "validation_buttons": False,
            },
        )

    @app.get("/validate", dependencies=[Depends(hascap("validate"))])
    async def validate_page(request: Request):
        """Render the validation page."""
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "is_validator": True,
                "validation_buttons": True,
            },
        )

    return app
