"""
FastAPI route for serving HTML reports from the data path.
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from ..config import config


def install_reports(app: FastAPI) -> FastAPI:
    """Install the reports serving route."""

    hascap = app.auth.get_email_capability

    @app.get("/reports/{path:path}", dependencies=[Depends(hascap("dev"))])
    async def route_reports(path: str):
        reports_dir = (config.data_path / "reports").resolve()
        report_path = (reports_dir / path).resolve()

        # Security check: ensure the path is within the reports directory
        try:
            report_path.relative_to(reports_dir)
        except ValueError:
            raise HTTPException(status_code=404, detail="Report not found")

        if not report_path.exists() or not report_path.is_file():
            raise HTTPException(status_code=404, detail="Report not found")

        return FileResponse(report_path)

    return app
