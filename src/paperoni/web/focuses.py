"""
FastAPI route for editing focuses with a web interface.
"""

from fastapi import Depends, FastAPI, Request

from .helpers import render_template


def install_focuses(app: FastAPI) -> FastAPI:
    """Install the focuses web interface route."""

    hascap = app.auth.get_email_capability

    @app.get("/focuses", dependencies=[Depends(hascap("admin"))])
    async def focuses_page(request: Request):
        """Render the focuses edit page."""
        return render_template("focuses.html", request)

    return app
