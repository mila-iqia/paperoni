"""
FastAPI route for editing papers with a web interface.
"""

from fastapi import Depends, FastAPI, Request
from serieux import deserialize

from .helpers import render_template


def install_edit(app: FastAPI) -> FastAPI:
    """Install the edit web interface route."""

    hascap = app.auth.get_email_capability

    @app.get("/edit/{paper_id}")
    async def edit_page(
        request: Request,
        paper_id: int | str,
        user: str = Depends(hascap("search", redirect=True)),
    ):
        """Render the paper edit page. Use ?suggest=1 for suggest mode (default for non-validators)."""
        validate = deserialize(app.auth.capabilities.captype, "validate")
        has_validate = app.auth.capabilities.check(user, validate)

        suggest_param = request.query_params.get("suggest")
        if suggest_param is not None:
            suggest = suggest_param.lower() in ("1", "true", "yes")
        else:
            suggest = not has_validate

        return render_template(
            "edit.html",
            request,
            paper_id=repr(paper_id),
            suggest=suggest,
            has_validate=has_validate,
        )

    return app
