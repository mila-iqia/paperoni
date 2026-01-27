"""
FastAPI route for searching papers with a web interface.
"""

from fastapi import Depends, FastAPI, Request
from serieux import deserialize

from .helpers import render_template


def install_search(app: FastAPI) -> FastAPI:
    """Install the search web interface route."""

    hascap = app.auth.get_email_capability

    @app.get("/search")
    async def search_page(
        request: Request,
        user: str = Depends(hascap("search", redirect=True)),
    ):
        """Render the search page."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        is_validator = app.auth.capabilities.check(user, validate)
        return render_template(
            "search.html",
            request,
            is_validator=is_validator,
            validation_buttons=False,
        )

    @app.get("/validate", dependencies=[Depends(hascap("validate", redirect=True))])
    async def validate_page(request: Request):
        """Render the validation page."""
        return render_template(
            "validate.html",
            request,
            is_validator=True,
            validation_buttons=True,
        )

    @app.get("/workset")
    async def workset_page(
        request: Request,
        user: str = Depends(hascap("admin", redirect=True)),
    ):
        """Render the workset page."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        is_validator = app.auth.capabilities.check(user, validate)
        return render_template(
            "workset.html",
            request,
            is_validator=is_validator,
            validation_buttons=False,
        )

    @app.get("/exclusions", dependencies=[Depends(hascap("validate", redirect=True))])
    async def exclusions_page(request: Request):
        """Render the exclusions management page."""
        return render_template(
            "exclusions.html",
            request,
            is_validator=True,
            validation_buttons=False,
        )

    return app
