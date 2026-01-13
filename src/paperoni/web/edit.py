"""
FastAPI route for editing papers with a web interface.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates

here = Path(__file__).parent


def install_edit(app: FastAPI) -> FastAPI:
    """Install the edit web interface route."""

    hascap = app.auth.get_email_capability
    templates = Jinja2Templates(directory=str((here / "templates").resolve()))

    @app.get("/edit/{paper_id}", dependencies=[Depends(hascap("validate"))])
    async def edit_page(request: Request, paper_id: int):
        """Render the paper edit page."""
        return templates.TemplateResponse(
            "edit.html",
            {
                "request": request,
                "paper_id": paper_id,
                "has_logo": app.has_logo,
                "has_custom_css": app.has_custom_css,
                "help_section": "edit",
            },
        )

    return app
