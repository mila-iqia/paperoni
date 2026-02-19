"""
FastAPI routes for serving markdown-based pages (index, help).
"""

from pathlib import Path

import markdown
from fastapi import Depends, FastAPI, HTTPException, Request

from ..config import config
from .helpers import render_template

here = Path(__file__).parent


def get_markdown_content(filename: str) -> str:
    """Get markdown content from custom assets or package assets."""
    # Try custom assets first
    if config.server.assets:
        custom_path = Path(config.server.assets) / filename
        if custom_path.exists():
            return custom_path.read_text(encoding="utf-8")

    # Fall back to package assets
    package_path = here / "assets" / filename
    if package_path.exists():
        return package_path.read_text(encoding="utf-8")

    return None


def _render_markdown_page(filename, page_title, request):
    md_content = get_markdown_content(filename)
    if md_content is None:
        raise HTTPException(status_code=404, detail=f"{page_title} page not found")

    html_content = markdown.markdown(
        md_content, extensions=["extra", "codehilite", "toc", "attr_list"]
    )

    return render_template(
        "markdown.html",
        request,
        help_section=False,
        page_title=page_title,
        content=html_content,
    )


def install_pages(app: FastAPI) -> FastAPI:
    """Install the markdown page routes."""

    hascap = app.auth.get_email_capability

    @app.get("/")
    async def index_page(request: Request):
        """Render the index page from markdown."""
        return _render_markdown_page("index.md", "Home", request)

    @app.get("/help")
    async def help_page(request: Request):
        """Render the help page."""
        return _render_markdown_page("help.md", "Help", request)

    @app.get("/admin", dependencies=[Depends(hascap("admin", redirect=True))])
    async def admin_page(request: Request):
        """Render the admin page from markdown."""
        return _render_markdown_page("admin.md", "Admin", request)

    return app
