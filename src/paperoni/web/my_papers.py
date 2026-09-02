"""
FastAPI route for the "My Papers" web interface: papers associated with the
logged-in user's email address.
"""

from fastapi import Depends, FastAPI, Request
from serieux import deserialize

from .helpers import render_template


def install_my_papers(app: FastAPI) -> FastAPI:
    """Install the "my papers" web interface route."""

    hascap = app.auth.get_email_capability

    @app.get("/my-papers", include_in_schema=False)
    async def my_papers_page(
        request: Request,
        user: str = Depends(hascap("search", redirect=True)),
    ):
        """Render the "my papers" page. Use ?suggest=1 to force suggest mode
        (e.g. for a validator to test the suggestion flow); default is
        suggest mode for non-validators, direct edits for validators."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        has_validate = app.auth.capabilities.check(user, validate)

        suggest_param = request.query_params.get("suggest")
        if suggest_param is not None:
            suggest = suggest_param.lower() in ("1", "true", "yes")
        else:
            suggest = not has_validate

        return render_template(
            "my_papers.html",
            request,
            user_email=user,
            suggest=suggest,
            help_section="/help#my-papers",
        )

    return app
