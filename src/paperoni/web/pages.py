"""
FastAPI routes for serving markdown-based pages (index, help).
"""

from pathlib import Path

import markdown
from fastapi import Depends, FastAPI, HTTPException, Request

from ..config import config
from .helpers import render_template

here = Path(__file__).parent


def get_markdown_content(filename: str) -> str | None:
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


def _localized_markdown_filename(base_filename: str) -> str:
    """Return the -fr variant filename for a base filename (e.g. index.md -> index-fr.md)."""
    stem = Path(base_filename).stem
    suffix = Path(base_filename).suffix
    return f"{stem}-fr{suffix}"


def _render_markdown_page(filename: str, page_title: str, request):
    md_content = get_markdown_content(filename)
    if md_content is None:
        raise HTTPException(status_code=404, detail=f"{page_title} page not found")

    extensions = ["extra", "codehilite", "toc", "attr_list"]
    content_en = markdown.markdown(md_content, extensions=extensions)

    localized_filename = _localized_markdown_filename(filename)
    md_content_fr = get_markdown_content(localized_filename)
    content_fr = (
        markdown.markdown(md_content_fr, extensions=extensions) if md_content_fr else None
    )

    return render_template(
        "markdown.html",
        request,
        help_section=False,
        page_title=page_title,
        content_en=content_en,
        content_fr=content_fr,
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
