"""
FastAPI route for editing papers with a web interface.
"""

from fastapi import Depends, FastAPI, Request

from .helpers import render_template


def install_edit(app: FastAPI) -> FastAPI:
    """Install the edit web interface route."""

    hascap = app.auth.get_email_capability

    @app.get("/edit/{paper_id}", dependencies=[Depends(hascap("validate"))])
    async def edit_page(request: Request, paper_id: int):
        """Render the paper edit page."""
        return render_template("edit.html", request, paper_id=paper_id)

    return app
