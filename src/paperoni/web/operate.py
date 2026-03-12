"""
FastAPI routes for the operate functionality (UI and API).

Only installed when config.server.enable_operate is True.
"""

import traceback
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request

from ..__main__ import Coll
from ..config import config
from ..operations import from_code
from .helpers import render_template
from .restapi import DiffResponse, PaperDiff, SearchRequest


@dataclass
class OperateResponse(DiffResponse):
    matched: int = 0
    unmatched: int = 0


@dataclass(kw_only=True)
class OperateRequest(SearchRequest):
    """Request model for operate (POST body)."""

    operation: str
    mode: Literal["test", "simulate", "apply"] = "test"


def install_operate(app: FastAPI) -> FastAPI:
    """Install the operate UI and API routes, if enable_operate is True."""

    if not config.server.enable_operate:
        return app

    hascap = app.auth.get_email_capability
    prefix = "/api/v1"

    @app.get("/operate")
    async def operate_page(
        request: Request,
        user: str = Depends(hascap("admin", redirect=True)),
    ):
        """Render the operate page."""
        return render_template("operate.html", request)

    def _run_operate(operation_obj, selected):
        results = []
        for p in selected:
            result = operation_obj(p)
            results.append(
                PaperDiff(
                    matched=result.changed,
                    current=p,
                    new=result.new if result.changed else None,
                )
            )
        return results

    @app.post(
        f"{prefix}/operate",
        response_model=OperateResponse,
        dependencies=[Depends(hascap("admin"))],
    )
    async def operate_papers_post(request: OperateRequest):
        try:
            operation_obj = from_code(request.operation)
            coll = Coll(command=None)

            matched = 0
            unmatched = 0
            results = []

            match request.mode:
                case "test":
                    selected = await request.run(coll)
                    results = _run_operate(operation_obj, selected)
                    matched = sum(r.matched for r in results)
                    unmatched = sum(not r.matched for r in results)

                case "simulate":
                    limit = request.limit
                    offset = request.offset
                    request.limit = request.offset = 0
                    all_matches = await request.run(coll)
                    results = _run_operate(operation_obj, all_matches)
                    matched = sum(r.matched for r in results)
                    unmatched = sum(not r.matched for r in results)
                    results = results[offset : offset + limit]

                case "apply":
                    request.limit = request.offset = 0
                    all_matches = await request.run(coll)
                    diffs = _run_operate(operation_obj, all_matches)
                    matched = sum(r.matched for r in diffs)
                    unmatched = sum(not r.matched for r in diffs)
                    edits = [
                        d.new
                        for d in diffs
                        if d.matched and d.new and "mark:delete" not in d.new.flags
                    ]
                    deletions = [
                        d.current.id
                        for d in diffs
                        if d.matched and d.new and "mark:delete" in d.new.flags
                    ]
                    await coll.collection.add_papers(
                        edits, force=True, ignore_exclusions=True
                    )
                    await coll.collection.delete_ids(deletions)
                    results = []

            return OperateResponse(
                results=results,
                next_offset=request.offset + len(results),
                total=await request.count(coll),
                matched=matched,
                unmatched=unmatched,
            )
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=traceback.format_exc(),
            )

    return app
