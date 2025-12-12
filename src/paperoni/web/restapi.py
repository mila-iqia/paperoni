"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import datetime
import itertools
from dataclasses import dataclass, field
from types import NoneType
from typing import Generator, Iterable, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from serieux import auto_singleton, deserialize, serialize

from ..__main__ import Coll, Focus, Formatter, Fulltext, Work
from ..config import config
from ..fulltext.locate import URL
from ..fulltext.pdf import PDF
from ..model.classes import CollectionPaper, Paper, PaperInfo
from ..model.focus import Focuses, Scored
from ..utils import url_to_id


@auto_singleton("void")
class VoidFormatter(Formatter):
    def __call__(self, things):
        pass


@dataclass
class PagingMixin:
    """Mixin for paging."""

    # Results offset
    offset: int = field(default=0)
    # Max number of results to return
    size: int = field(default=100)

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
        size: int = None,
    ) -> Iterable:
        if offset is None:
            offset = self.offset or 0
        if size is None:
            size = self.size or 100

        size = min(size, config.server.max_results)

        self._count = 0
        self._next_offset = offset
        for entry in itertools.islice(iterable, offset, offset + size):
            self._count += 1
            self._next_offset += 1
            yield entry

        if self._count < size:
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
class ViewResponse(PagingResponseMixin):
    """Response model for work state paper view."""

    results: list[Scored[Paper]]


@dataclass
class AutoFocusRequest(Focus.AutoFocus):
    """Request model for autofocus."""

    pass


def _search(request: dict):
    request: SearchRequest = deserialize(SearchRequest, request)

    coll = Coll(command=None)

    # Perform search using the collection's search method
    all_matches = request.run(coll)
    results = list(request.slice(all_matches))

    return results, request.count, request.next_offset, len(all_matches)


def _work_view(request: dict):
    request: ViewRequest = deserialize(ViewRequest, request)

    """Search for papers in the collection."""
    work = Work(command=request, work_file=config.work_file)

    papers: list[Scored[Paper]] = list(request.slice(work.run()))

    return papers, request.count, request.next_offset, len(work.top)


def _locate_fulltext(request: dict):
    request: LocateFulltextRequest = deserialize(LocateFulltextRequest, request)
    all_urls = request.run()
    urls = list(request.slice(all_urls))
    return urls, request.count, request.next_offset, len(all_urls)


def _download_fulltext(request: dict):
    request: DownloadFulltextRequest = deserialize(DownloadFulltextRequest, request)
    return request.run()


async def run_in_process_pool(func, *args):
    # TODO: find a way to serialize a dynamically modified config using
    # gifnoc.overlay such that we serialize / deserialize quickly properties
    # like collection. Currently, serialize(config) fails with
    # serieux.exc.ValidationError: At path (at root): Cannot serialize object of type 'Proxy'
    if config.server.process_pool is None:
        return func(*args)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(config.server.process_pool, func, *args)


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

    @app.get(
        f"{prefix}/search",
        response_model=SearchResponse,
        dependencies=[Depends(hascap("search"))],
    )
    async def search_papers(request: SearchRequest = Depends()):
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
        work.run()

        return AddResponse(total=len(work.top))

    @app.get(f"{prefix}/work/view", response_model=ViewResponse)
    async def work_view_papers(
        request: ViewRequest = Depends(), user: str = Depends(hascap("admin"))
    ):
        papers, count, next_offset, total = await run_in_process_pool(
            _work_view, serialize(ViewRequest, request)
        )
        return ViewResponse(
            results=serialize(list[Scored[Paper]], papers),
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

        added = work.run()

        return IncludeResponse(total=added)

    @app.get(
        f"{prefix}/focus/auto",
        response_model=Focuses,
        dependencies=[Depends(hascap("admin"))],
    )
    async def autofocus(request: AutoFocusRequest = Depends()):
        """Autofocus the collection."""
        focus = Focus(command=None)

        return request.run(focus)

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
