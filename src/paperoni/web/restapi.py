"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import datetime
import itertools
from dataclasses import dataclass, field
from types import NoneType
from typing import Generator, Iterable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from serieux import auto_singleton, deserialize, serialize

from ..__main__ import Coll, Focus, Formatter, Fulltext, Work
from ..config import config
from ..fulltext.locate import URL
from ..fulltext.pdf import PDF
from ..model.classes import CollectionPaper, Paper, PaperInfo
from ..model.focus import Focuses, Scored
from ..model.merge import PaperWorkingSet
from ..utils import url_to_id


@auto_singleton("void")
class VoidFormatter(Formatter):
    def __call__(self, things):
        pass


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

    results: list[CollectionPaper]


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

    def iterate(self, **kwargs) -> Generator[PaperInfo, None, None]:
        papers = deserialize(list[Paper], self.papers)

        for paper in papers:
            yield PaperInfo(
                key=f"user:{self.user}",
                acquired=datetime.datetime.now(datetime.timezone.utc),
                paper=paper,
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
class EditRequest:
    """Request model for editing a paper."""

    paper: dict


@dataclass
class EditResponse:
    """Response model for editing a paper."""

    success: bool
    message: str
    paper: CollectionPaper | None = None


@dataclass
class ViewResponse(PagingResponseMixin):
    """Response model for work state paper view."""

    results: list[Scored[Paper]]


@dataclass
class AutoFocusRequest(Focus.AutoFocus):
    """Request model for autofocus."""

    pass


async def _search(request: dict):
    request: SearchRequest = deserialize(SearchRequest, request)

    coll = Coll(command=None)

    # Perform search using the collection's search method
    all_matches = await request.run(coll)
    results = list(request.slice(all_matches))

    return results, request.count, request.next_offset, len(all_matches)


async def _work_view(request: dict):
    request: ViewRequest = deserialize(ViewRequest, request)

    """Search for papers in the collection."""
    work = Work(command=request, work_file=config.work_file)

    worksets: list[Scored[PaperWorkingSet]] = list(request.slice(await work.run()))

    return worksets, request.count, request.next_offset, len(work.top)


async def _locate_fulltext(request: dict):
    request: LocateFulltextRequest = deserialize(LocateFulltextRequest, request)
    all_urls = await request.run()
    urls = list(request.slice(all_urls))
    return urls, request.count, request.next_offset, len(all_urls)


async def _download_fulltext(request: dict):
    request: DownloadFulltextRequest = deserialize(DownloadFulltextRequest, request)
    return await request.run()


def _run_async_in_new_loop(func, *args):
    """Run an async function in a new event loop (for use in process pool)."""
    return asyncio.run(func(*args))


async def run_in_process_pool(func, *args):
    # TODO: find a way to serialize a dynamically modified config using
    # gifnoc.overlay such that we serialize / deserialize quickly properties
    # like collection. Currently, serialize(config) fails with
    # serieux.exc.ValidationError: At path (at root): Cannot serialize object of type 'Proxy'
    if config.server.process_pool is None:
        return await func(*args)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        config.server.process_pool, _run_async_in_new_loop, func, *args
    )


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
        results, count, next_offset, total = await run_in_process_pool(
            _search, serialize(SearchRequest, request)
        )
        return SearchResponse(
            results=results, count=count, next_offset=next_offset, total=total
        )

    @app.get(
        f"{prefix}/paper/{{paper_id}}",
        response_model=CollectionPaper,
        dependencies=[Depends(hascap("search"))],
    )
    async def get_paper(paper_id: int):
        """Get a single paper by ID."""
        coll = Coll(command=None)
        paper = coll.collection.find_by_id(paper_id)
        if paper is None:
            raise HTTPException(
                status_code=404, detail=f"Paper with ID {paper_id} not found"
            )
        return paper

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
        worksets, count, next_offset, total = await run_in_process_pool(
            _work_view, serialize(ViewRequest, request)
        )
        return ViewResponse(
            results=serialize(list[Scored[PaperWorkingSet]], worksets),
            count=count,
            next_offset=next_offset,
            total=total,
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

        paper = coll.collection.find_by_id(request.paper_id)
        if paper is None:
            return SetFlagResponse(
                success=False, message=f"Paper with ID {request.paper_id} not found"
            )

        if request.value:
            paper.flags.add(request.flag)
        else:
            paper.flags.discard(request.flag)

        coll.collection.edit_paper(paper)

        return SetFlagResponse(
            success=True,
            message=f"Flag '{request.flag}' {'set' if request.value else 'unset'} for paper {request.paper_id}",
        )

    @app.post(
        f"{prefix}/edit",
        response_model=EditResponse,
        dependencies=[Depends(hascap("validate"))],
    )
    async def edit_paper(request: EditRequest):
        """Edit an existing paper in the collection."""
        coll = Coll(command=None)

        # Deserialize the paper from the request
        paper = deserialize(CollectionPaper, request.paper)

        # Verify the paper has an ID
        if paper.id is None:
            return EditResponse(
                success=False,
                message="Paper must have an ID to be edited",
                paper=None,
            )

        # Verify the paper exists in the collection
        existing_paper = coll.collection.find_by_id(paper.id)
        if existing_paper is None:
            return EditResponse(
                success=False,
                message=f"Paper with ID {paper.id} not found",
                paper=None,
            )

        # Update the paper in the collection
        coll.collection.edit_paper(paper)

        return EditResponse(
            success=True,
            message=f"Paper {paper.id} updated successfully",
            paper=paper,
        )

    @app.get(
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
        results, count, next_offset, total = await run_in_process_pool(
            _locate_fulltext, serialize(LocateFulltextRequest, request)
        )
        return LocateFulltextResponse(
            results=results,
            count=count,
            next_offset=next_offset,
            total=total,
        )

    @app.get(
        f"{prefix}/fulltext/download",
        dependencies=[Depends(hascap("user"))],
    )
    async def download_fulltext(request: DownloadFulltextRequest):
        """Download fulltext for a paper."""
        pdf = await run_in_process_pool(
            _download_fulltext, serialize(DownloadFulltextRequest, request)
        )

        # Return as file download
        async def async_iter_pdf():
            with pdf.pdf_path.open("rb") as bf:
                while b := bf.read(1024):
                    yield b

        return StreamingResponse(
            async_iter_pdf(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{pdf.directory.name}.pdf"'
            },
        )

    return app
