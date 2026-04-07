"""
Helper functions for web routes.
"""

import re
import secrets
from functools import cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from serieux import deserialize

from ..config import config

here = Path(__file__).parent


_translations = deserialize(list[dict[str, str]], here / "assets" / "translate.json")
to_fr = {tr["en"]: tr["fr"] for tr in _translations}

# Replace <loc>...</loc> inner content with to_fr when cookie is fr
_LOC_PATTERN = re.compile(
    r"(<loc(?:\s[^>]*)?>)(.*?)(</loc>)",
    re.DOTALL,
)


def _replace_loc_with_fr(html: str) -> str:
    def replace_match(m: re.Match) -> str:
        opening, inner, closing = m.group(1), m.group(2), m.group(3)
        key = " ".join(inner.split()).strip()
        return opening + (to_fr.get(key, inner)) + closing

    return _LOC_PATTERN.sub(replace_match, html)


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

    If cookie paperoni-lang is "fr", replace <loc>...</loc> inner text with
    French from to_fr.

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

    nonce = secrets.token_urlsafe(16)
    context["csp_nonce"] = nonce

    tmpl = templates().env.get_template(template_name)
    body = tmpl.render(**context)

    if request.cookies.get("paperoni-lang") == "fr":
        body = _replace_loc_with_fr(body)

    delivr = " https://cdn.jsdelivr.net" if config.server.enable_operate else ""

    csp = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'{delivr}; "
        f"style-src 'self' 'unsafe-inline'{delivr}; "
        f"worker-src 'self' blob:; "
        f"img-src 'self'; "
        f"connect-src 'self'{delivr}; "
        f"font-src 'self'{delivr}; "
        f"frame-ancestors 'none'; "
        f"form-action 'self'"
    )
    response = HTMLResponse(content=body)
    response.headers["Content-Security-Policy"] = csp
    return response
