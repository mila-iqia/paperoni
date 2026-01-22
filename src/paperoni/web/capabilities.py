"""
FastAPI routes for user capabilities management interface.
"""

from easy_oauth import OAuthManager
from fastapi import Depends, FastAPI, Request

from .helpers import render_template


def install_capabilities(app: FastAPI) -> FastAPI:
    """Install the capabilities management routes."""

    auth: OAuthManager = app.auth
    hascap = auth.get_email_capability
    user_management_cap = auth.user_management_capability

    # Use user_management capability if available, otherwise fall back to admin
    required_cap = user_management_cap if user_management_cap else "admin"

    @app.get("/capabilities")
    async def capabilities_page(
        request: Request, user: str = Depends(hascap(required_cap, redirect=True))
    ):
        """Render the capabilities management page."""
        return render_template(
            "capabilities.html",
            request,
            help_section="capabilities",
            page_title="Manage Capabilities",
            oauth_prefix=auth.prefix,
        )

    return app
