"""
Helper functions for web routes.
"""

from functools import cache
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from ..config import config

here = Path(__file__).parent


@cache
def templates():
    return Jinja2Templates(directory=str((here / "templates").resolve()))


def render_template(
    template_name: str,
    request: Request,
    help_section: str | bool = True,
    **kwargs,
):
    """
    Render a template with standard context variables.

    Args:
        template_name: Name of the template file
        request: FastAPI Request object
        **kwargs: Additional context variables to pass to the template

    Returns:
        TemplateResponse
    """
    # Check for logo and custom CSS
    has_logo = False
    has_custom_css = False

    if config.server.assets:
        custom_assets_path = Path(config.server.assets)
        has_logo = (custom_assets_path / "logo.png").exists()
        has_custom_css = (custom_assets_path / "style.css").exists()

    logged_in = request.session.get("user", None) is not None
    if help_section is True:
        help_section = template_name.split(".")[0]

    context = {
        "request": request,
        "has_logo": has_logo,
        "has_custom_css": has_custom_css,
        "logged_in": logged_in,
        "help_section": help_section,
        **kwargs,
    }

    return templates().TemplateResponse(template_name, context)
