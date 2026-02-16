import importlib.metadata
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from easy_oauth import OAuthManager
from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from serieux import serialize
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

import paperoni

from ..config import config

app_logger = logging.getLogger(__name__)

here = Path(__file__).parent


@dataclass
class StartupData:
    file: Path | None
    mtime: float | None
    start_time: float

    @classmethod
    def make(cls):
        filename = os.environ.get("GIFNOC_FILE", None)
        if filename is None:
            return cls(file=None, mtime=None, start_time=time.time())
        main_filename = filename.split(",")[0]
        file = Path(main_filename)
        return cls(
            file=file,
            mtime=file.stat().st_mtime if file and file.exists() else None,
            start_time=time.time(),
        )


@dataclass
class ConfigStatus:
    stale: bool
    file: Path | None
    mtime: float | None
    uptime: float

    @classmethod
    def check(cls, previous: StartupData):
        current = StartupData.make()
        return cls(
            stale=previous.mtime is None
            or current.mtime is None
            or current.mtime > previous.mtime,
            file=previous.file,
            mtime=previous.mtime,
            uptime=current.start_time - previous.start_time,
        )


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

    initial = StartupData.make()

    @app.get("/config-status")
    def config_status(fail_on_stale: bool = False) -> ConfigStatus:
        status = ConfigStatus.check(initial)
        if fail_on_stale and status.stale:
            code = 500
        else:
            code = 200
        return JSONResponse(
            status_code=code,
            content=serialize(ConfigStatus, status),
        )

    for entry_point in importlib.metadata.entry_points(group="paperoni.web"):
        func = entry_point.load()
        func(app)

    return app
