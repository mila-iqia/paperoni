"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import datetime
import itertools
from dataclasses import dataclass, field, replace
from types import NoneType
from typing import Any, AsyncGenerator, Generator, Iterable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from serieux import auto_singleton, deserialize, serialize

from ..__main__ import Coll, Focus, Formatter, Fulltext, Work
from ..config import config
from ..fulltext.locate import URL
from ..fulltext.pdf import PDF
from ..model.classes import Paper as _Paper
from ..model.focus import Focuses, Scored
from ..model.merge import PaperWorkingSet
from ..utils import url_to_id


@auto_singleton("void")
class VoidFormatter(Formatter):
    def __call__(self, things):
        pass


@dataclass
class Paper(_Paper):
    # Pydantic will not accept dict[str, JSON], so we cheat here
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class PagingMixin:
    """Mixin for paging."""

    # Pagination offset
    offset: int = field(default=0)
    # Maximum number of results to return
    limit: int = field(default=100)

    _count: int | None = field(repr=False, compare=False, default=None)
    _next_offset: int | None = field(repr=False, compare=False, default=None)

    @property
    def count(self) -> int:
        return self._count

    @property
    def next_offset(self) -> int:
        return self._next_offset

    def slice(
        self,
        iterable: Iterable,
        *,
        offset: int = None,
        limit: int = None,
    ) -> Iterable:
        if offset is None:
            offset = self.offset or 0
        if limit is None:
            limit = self.limit or 100

        limit = min(limit, config.server.max_results)

        self._count = 0
        self._next_offset = offset
        for entry in itertools.islice(iterable, offset, offset + limit):
            self._count += 1
            self._next_offset += 1
            yield entry

        if self._count < limit:
            # No more results
            self._next_offset = None


@dataclass
class PagingResponseMixin:
    """Mixin for paging response."""

    results: list
    count: int
    next_offset: int | None
    total: int


@dataclass
class SearchRequest(PagingMixin, Coll.Search):
    """Request model for paper search."""

    # TODO: hide the format field from the api endpoint schema
    format: NoneType = field(
        init=False,
        repr=False,
        compare=False,
        default_factory=lambda: VoidFormatter,
        metadata={"ignore": True},
    )

    def __post_init__(self):
        # Type hinting for format
        self.format: VoidFormatter = self.format


@dataclass
class SearchResponse(PagingResponseMixin):
    """Response model for paper search."""

    results: list[Paper]


@dataclass
class LocateFulltextRequest(PagingMixin, Fulltext.Locate):
    """Request model for fulltext locate."""

    def format(self, urls: list[URL]):
        return VoidFormatter(urls)


@dataclass
class LocateFulltextResponse(PagingResponseMixin):
    """Response model for fulltext locate."""

    results: list[URL]


@dataclass
class DownloadFulltextRequest(Fulltext.Download):
    """Request model for fulltext download."""

    ref: str | list[str]
    cache_policy: Literal["no_download"] = field(
        repr=False, compare=False, default="no_download"
    )

    def format(self, pdf: PDF):
        VoidFormatter([pdf])

    def __post_init__(self):
        if isinstance(self.ref, str):
            self.ref = [self.ref]
        else:
            self.ref = self.ref

        self.ref = list(
            map(
                lambda x: (
                    ":".join(url_to_id(x) or ["", ""]) if x.startswith("http") else x
                ),
                self.ref,
            )
        )


@dataclass
class IncludeRequest(Work.Include):
    """Request model for work state paper include."""

    # Minimum score for saving
    score: float = field(
        default_factory=lambda: max(f.score for f in config.focuses.focuses)
    )


@dataclass
class IncludeResponse:
    """Response model for work state paper include."""

    total: int


@dataclass
class ViewRequest(PagingMixin, Work.View):
    """Request model for work state paper view."""

    what: Literal["paper"] = field(
        init=False, repr=False, compare=False, default="paper", metadata={"ignore": True}
    )
    n: NoneType = field(
        init=False, repr=False, compare=False, default=None, metadata={"ignore": True}
    )

    # TODO: hide the format field from the api endpoint schema
    format: NoneType = field(
        init=False,
        repr=False,
        compare=False,
        default_factory=lambda: VoidFormatter,
        metadata={"ignore": True},
    )

    def __post_init__(self):
        # Type hinting for format
        self.format: VoidFormatter = self.format


@dataclass
class AddRequest(Work.Get):
    # disable command
    command: NoneType = field(init=False, repr=False, compare=False, default=None)

    papers: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.user: str = None

    def iterate(self, **kwargs) -> Generator[Paper, None, None]:
        papers = deserialize(list[_Paper], self.papers)

        for paper in papers:
            yield replace(
                paper,
                key=f"user:{self.user}",
                acquired=datetime.datetime.now(datetime.timezone.utc),
                info={"added_by": {"user": self.user}},
            )


@dataclass
class AddResponse:
    """Response model for work state paper add."""

    total: int


@dataclass
class SetFlagRequest:
    """Request model for setting a flag on a paper."""

    paper_id: int
    flag: str
    value: bool = True


@dataclass
class SetFlagResponse:
    """Response model for setting a flag on a paper."""

    success: bool
    message: str


@dataclass
class PaperIncludeRequest:
    """Request model for including new papers."""

    papers: list[dict]


@dataclass
class PaperIncludeResponse:
    """Response model for including new papers."""

    success: bool
    message: str
    count: int = 0
    ids: list[int | str] = field(default_factory=list)


@dataclass
class DeletePapersRequest:
    """Request model for deleting papers."""

    ids: list[int]


@dataclass
class DeletePapersResponse:
    """Response model for deleting papers."""

    success: bool
    message: str
    count: int


@dataclass
class ViewResponse(PagingResponseMixin):
    """Response model for work state paper view."""

    results: list[Scored[Paper]]


@dataclass
class AutoFocusRequest(Focus.AutoFocus):
    """Request model for autofocus."""

    pass


@dataclass
class ExclusionsListRequest(PagingMixin):
    """Request model for listing exclusions."""

    pass


@dataclass
class ExclusionsListResponse(PagingResponseMixin):
    """Response model for listing exclusions."""

    results: list[str]


@dataclass
class AddExclusionsRequest:
    """Request model for adding exclusions."""

    exclusions: list[str]


@dataclass
class AddExclusionsResponse:
    """Response model for adding exclusions."""

    success: bool
    message: str
    count: int


@dataclass
class RemoveExclusionsRequest:
    """Request model for removing exclusions."""

    exclusions: list[str]


@dataclass
class RemoveExclusionsResponse:
    """Response model for removing exclusions."""

    success: bool
    message: str
    count: int


def install_api(app) -> FastAPI:
    prefix = "/api/v1"

    hascap = app.auth.get_email_capability

    @app.get(f"{prefix}")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": app.title,
            "version": app.version,
        }

    def parse_search_request(
        request: SearchRequest = Depends(),
        flags: set[str] = Query(default=None),
    ) -> SearchRequest:
        """Parse search request with proper handling of flags list parameter."""
        # Add flags if provided (FastAPI's Query() handles set parsing)
        if flags:
            request.flags = flags

        return request

    @app.get(
        f"{prefix}/search",
        response_model=SearchResponse,
        dependencies=[Depends(hascap("search"))],
    )
    async def search_papers(request: SearchRequest = Depends(parse_search_request)):
        """Search for papers in the collection."""
        coll = Coll(command=None)

        # Perform search using the collection's search method
        all_matches = await request.run(coll)
        results = list(request.slice(all_matches))

        return SearchResponse(
            results=results,
            count=request.count,
            next_offset=request.next_offset,
            total=len(all_matches),
        )

    @app.get(
        f"{prefix}/paper/{{paper_id}}",
        response_model=Paper,
        dependencies=[Depends(hascap("search"))],
    )
    async def get_paper(paper_id: int):
        """Get a single paper by ID."""
        coll = Coll(command=None)
        paper = await coll.collection.find_by_id(paper_id)
        if paper is None:
            raise HTTPException(
                status_code=404, detail=f"Paper with ID {paper_id} not found"
            )
        # FastAPI requires this conversion, it'll be serialized so it's fine
        return Paper(**vars(paper))

    @app.post(f"{prefix}/work/add", response_model=AddResponse)
    async def work_add_papers(request: AddRequest, user: str = Depends(hascap("admin"))):
        request.user = user

        work = Work(command=request, work_file=config.work_file)
        await work.run()

        return AddResponse(total=len(work.top))

    @app.get(f"{prefix}/work/view", response_model=ViewResponse)
    async def work_view_papers(
        request: ViewRequest = Depends(), user: str = Depends(hascap("admin"))
    ):
        work = Work(command=request, work_file=config.work_file)
        worksets: list[Scored[PaperWorkingSet]] = list(request.slice(await work.run()))

        return ViewResponse(
            results=serialize(list[Scored[PaperWorkingSet]], worksets),
            count=request.count,
            next_offset=request.next_offset,
            total=len(work.top),
        )

    @app.get(
        f"{prefix}/work/include",
        response_model=IncludeResponse,
        dependencies=[Depends(hascap("admin"))],
    )
    async def work_include_papers(request: IncludeRequest):
        """Search for papers in the collection."""
        work = Work(command=request, work_file=config.work_file)

        added = await work.run()

        return IncludeResponse(total=added)

    @app.post(
        f"{prefix}/set_flag",
        response_model=SetFlagResponse,
        dependencies=[Depends(hascap("admin"))],
    )
    async def set_flag(request: SetFlagRequest):
        """Set a flag on a paper in the collection."""
        coll = Coll(command=None)

        paper = await coll.collection.find_by_id(request.paper_id)
        if paper is None:
            return SetFlagResponse(
                success=False, message=f"Paper with ID {request.paper_id} not found"
            )

        if request.value:
            paper.flags.add(request.flag)
        else:
            paper.flags.discard(request.flag)

        await coll.collection.edit_paper(paper)

        return SetFlagResponse(
            success=True,
            message=f"Flag '{request.flag}' {'set' if request.value else 'unset'} for paper {request.paper_id}",
        )

    @app.post(
        f"{prefix}/include",
        response_model=PaperIncludeResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def include_papers(request: PaperIncludeRequest):
        """Include papers in the collection."""
        coll = Coll(command=None)

        # Deserialize the papers from the request
        papers = deserialize(list[_Paper], request.papers)

        # Update the papers in the collection
        # We use add_papers which handles updates/merges
        try:
            added_ids = await coll.collection.add_papers(papers, force=True)
            return PaperIncludeResponse(
                success=True,
                message=f"Processed {len(added_ids)} paper(s)",
                count=len(added_ids),
                ids=added_ids,
            )
        except Exception as e:
            return PaperIncludeResponse(
                success=False,
                message=f"Error processing papers: {e}",
                count=0,
            )

    @app.get(f"{prefix}/focuses")
    async def get_focuses():
        """Get the current configuration focuses with main and auto sublists."""
        return serialize(Focuses, config.focuses._obj)

    @app.post(f"{prefix}/focuses", dependencies=[Depends(hascap("admin"))])
    async def set_focuses(new_focuses: dict):
        """Update the configuration focuses (main and auto sublists)."""
        if not hasattr(config.focuses, "save"):
            raise HTTPException(
                status_code=501,
                detail="The current configuration does not support saving focuses.",
            )

        focuses = deserialize(Focuses, new_focuses)
        config.focuses.save(focuses)
        return {"success": True, "message": "Focuses updated successfully."}

    @app.post(
        f"{prefix}/delete",
        response_model=DeletePapersResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def delete_papers(request: DeletePapersRequest):
        """Delete papers from the collection."""
        coll = Coll(command=None)
        deleted = await coll.collection.delete_ids(request.ids)
        return DeletePapersResponse(
            success=True,
            message=f"Deleted {deleted} paper(s)",
            count=deleted,
        )

    @app.post(
        f"{prefix}/focus/auto",
        response_model=Focuses,
        dependencies=[Depends(hascap("admin"))],
    )
    async def autofocus(request: AutoFocusRequest = Depends()):
        """Autofocus the collection."""
        focus = Focus(command=None)

        return await request.run(focus)

    @app.get(
        f"{prefix}/fulltext/locate",
        response_model=LocateFulltextResponse,
        dependencies=[Depends(hascap("user"))],
    )
    async def locate_fulltext(request: LocateFulltextRequest):
        """Locate fulltext urls for a paper."""
        all_urls = await request.run()
        urls = list(request.slice(all_urls))
        return LocateFulltextResponse(
            results=urls,
            count=request.count,
            next_offset=request.next_offset,
            total=len(all_urls),
        )

    @app.get(
        f"{prefix}/fulltext/download",
        dependencies=[Depends(hascap("user"))],
    )
    async def download_fulltext(request: DownloadFulltextRequest):
        """Download fulltext for a paper."""
        pdf = await request.run()

        # Return as file download
        async def async_iter_pdf() -> AsyncGenerator[bytes, None]:
            with pdf.pdf_path.open("rb") as bf:
                # Read 64KB at a time
                while b := bf.read(64 * 1024):
                    yield b

        return StreamingResponse(
            async_iter_pdf(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{pdf.directory.name}.pdf"'
            },
        )

    @app.get(
        f"{prefix}/exclusions",
        response_model=ExclusionsListResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def list_exclusions(request: ExclusionsListRequest = Depends()):
        """List exclusions with pagination."""
        coll = Coll(command=None)
        all_exclusions = await coll.collection.exclusions()
        # Convert set to sorted list for consistent pagination
        sorted_exclusions = sorted(all_exclusions)
        results = list(request.slice(sorted_exclusions))

        return ExclusionsListResponse(
            results=results,
            count=request.count,
            next_offset=request.next_offset,
            total=len(sorted_exclusions),
        )

    @app.post(
        f"{prefix}/exclusions",
        response_model=AddExclusionsResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def add_exclusions(request: AddExclusionsRequest):
        """Add exclusions to the collection."""
        coll = Coll(command=None)
        await coll.collection.add_exclusions(request.exclusions)
        added = len(request.exclusions)
        return AddExclusionsResponse(
            success=True,
            message=f"Added {added} exclusion(s)",
            count=added,
        )

    @app.delete(
        f"{prefix}/exclusions",
        response_model=RemoveExclusionsResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def remove_exclusions(request: RemoveExclusionsRequest):
        """Remove exclusions from the collection."""
        coll = Coll(command=None)
        await coll.collection.remove_exclusions(request.exclusions)
        removed = len(request.exclusions)
        return RemoveExclusionsResponse(
            success=True,
            message=f"Removed {removed} exclusion(s)",
            count=removed,
        )

    @app.get(
        f"{prefix}/export/data",
        dependencies=[Depends(hascap("dev"))],
    )
    async def download_data():
        """Stream the contents of the data directory as a tar.gz archive."""
        data_path = config.data_path

        if not data_path or not data_path.exists() or not data_path.is_dir():
            raise HTTPException(
                status_code=404,
                detail="The data directory does not exist or is not accessible",
            )

        data_path = data_path.resolve()

        async def stream_tar_gz() -> AsyncGenerator[bytes, None]:
            proc = await asyncio.create_subprocess_exec(
                "tar",
                "-czf",
                "-",
                "--cd",
                str(data_path),
                ".",
                stdout=asyncio.subprocess.PIPE,
            )
            try:
                while True:
                    # Read 64KB at a time
                    chunk = await proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await proc.wait()
                if proc.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail="Archive creation failed",
                    )

        return StreamingResponse(
            stream_tar_gz(),
            media_type="application/gzip",
            headers={"Content-Disposition": 'attachment; filename="data.tar.gz"'},
        )

    return app
