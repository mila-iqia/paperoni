import importlib.metadata
import logging

from easy_oauth import OAuthManager
from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException

import paperoni

from ..config import config
from .reports import install_reports
from .restapi import install_api

app_logger = logging.getLogger(__name__)


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
    install_api(app)
    install_reports(app)
    return app
