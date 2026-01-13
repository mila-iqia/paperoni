"""
FastAPI routes for serving markdown-based pages (index, help).
"""

from pathlib import Path

import markdown
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates

from ..config import config

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


def install_pages(app: FastAPI) -> FastAPI:
    """Install the markdown page routes."""

    hascap = app.auth.get_email_capability
    templates = Jinja2Templates(directory=str((here / "templates").resolve()))

    @app.get("/", dependencies=[Depends(hascap("search"))])
    async def index_page(request: Request):
        """Render the index page from markdown."""
        md_content = get_markdown_content("index.md")
        if md_content is None:
            raise HTTPException(status_code=404, detail="Index page not found")

        html_content = markdown.markdown(
            md_content, extensions=["extra", "codehilite", "toc", "attr_list"]
        )

        return templates.TemplateResponse(
            "markdown.html",
            {
                "request": request,
                "has_logo": app.has_logo,
                "has_custom_css": app.has_custom_css,
                "help_section": "",
                "page_title": "Home",
                "content": html_content,
            },
        )

    @app.get("/help", dependencies=[Depends(hascap("search"))])
    async def help_page(request: Request):
        """Render the help page."""
        md_content = get_markdown_content("help.md")
        if md_content is None:
            raise HTTPException(status_code=404, detail="Help page not found")

        html_content = markdown.markdown(
            md_content, extensions=["extra", "codehilite", "toc", "attr_list"]
        )

        return templates.TemplateResponse(
            "markdown.html",
            {
                "request": request,
                "has_logo": app.has_logo,
                "has_custom_css": app.has_custom_css,
                "help_section": "",
                "page_title": "Help",
                "content": html_content,
            },
        )

    return app
