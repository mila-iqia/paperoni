"""
FastAPI route for serving HTML reports from the data path.
"""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from ..config import config
from .helpers import render_template


def install_reports(app: FastAPI) -> FastAPI:
    """Install the reports serving route."""

    hascap = app.auth.get_email_capability

    @app.get("/logs/{path:path}", dependencies=[Depends(hascap("dev"))])
    async def route_logs(path: str):
        logs_dir = (config.data_path / "logs").resolve()
        report_path = (logs_dir / path).resolve()

        # Security check: ensure the path is within the logs directory
        try:
            report_path.relative_to(logs_dir)
        except ValueError:
            raise HTTPException(status_code=404, detail="Report not found")

        if not report_path.exists() or not report_path.is_file():
            raise HTTPException(status_code=404, detail="Report not found")

        return FileResponse(report_path)

    @app.get("/report/{path:path}", dependencies=[Depends(hascap("dev"))])
    async def route_report(request: Request, path: str):
        if not path:
            logs_dir = (config.data_path / "logs").resolve()
            # Sort newest to oldest by file modification time (descending)
            log_files = sorted(
                (f for f in logs_dir.glob("*.jsonl") if f.is_file()),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            report_basenames = [f.stem for f in log_files]
            links = [
                {"name": basename, "url": f"/report/{basename}"}
                for basename in report_basenames
            ]
            return render_template(
                "report_list.html",
                request,
                logs=links,
                help_section="reports",
            )
        else:
            return render_template("report.html", request, report_name=path)

    return app
