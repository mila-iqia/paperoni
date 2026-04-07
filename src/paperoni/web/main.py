import importlib.metadata
import logging
from pathlib import Path

from easy_oauth import OAuthManager
from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

import paperoni

from ..config import config

app_logger = logging.getLogger(__name__)

here = Path(__file__).parent


_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), accelerometer=(), magnetometer=(), payment=(), usb=(), gyroscope=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


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

    app.add_middleware(SecurityHeadersMiddleware)

    auth = config.server.auth or OAuthManager(server_metadata_url="n/a")
    auth.install(app)
    app.auth = auth

    app.mount("/assets", StaticFiles(directory=(here / "assets")), name="assets")

    # Mount custom assets if configured
    if config.server.assets and Path(config.server.assets).exists():
        app.mount("/custom", StaticFiles(directory=config.server.assets), name="custom")

    for entry_point in importlib.metadata.entry_points(group="paperoni.web"):
        func = entry_point.load()
        func(app)

    return app
