import importlib.metadata
import logging
from pathlib import Path

from easy_oauth import OAuthManager
from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

import paperoni

from ..config import config
from .edit import install_edit
from .pages import install_pages
from .reports import install_reports
from .restapi import install_api
from .search import install_search

app_logger = logging.getLogger(__name__)

here = Path(__file__).parent


def create_app():
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
    )

    @app.exception_handler(Exception)
    async def exception_handler(request, exc):
        app_logger.exception(exc)

        if getattr(exc, "status_code", None) is None:
            exc = HTTPException(status_code=500, detail="Internal Server Error")

        return await http_exception_handler(request, exc)

    auth = config.server.auth or OAuthManager(server_metadata_url="n/a")
    auth.install(app)
    app.auth = auth

    app.mount("/assets", StaticFiles(directory=(here / "assets")), name="assets")

    # Mount custom assets if configured
    if config.server.assets and Path(config.server.assets).exists():
        app.mount("/custom", StaticFiles(directory=config.server.assets), name="custom")
        custom_assets_path = Path(config.server.assets)
        app.has_logo = (custom_assets_path / "logo.png").exists()
        app.has_custom_css = (custom_assets_path / "style.css").exists()
    else:
        app.has_logo = False
        app.has_custom_css = False

    install_api(app)
    install_reports(app)
    install_search(app)
    install_edit(app)
    install_pages(app)
    return app
