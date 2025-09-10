"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import importlib.metadata
import itertools
from dataclasses import dataclass
from typing import Iterable, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

import paperoni

from .__main__ import Coll, Fulltext
from .fulltext.locate import URL
from .model.classes import Paper
from .utils import url_to_id


@dataclass
class PagingMixin:
    """Mixin for paging."""

    # Page of results to display
    page: int = None
    # Number of results to display per page
    per_page: int = None
    # Max number of papers to show
    limit: int = 100

    def slice(
        self,
        iterable: Iterable,
        *,
        page: int = None,
        per_page: int = None,
        limit: int = None,
    ) -> Iterable:
        if page is None:
            page = self.page or 0
        if per_page is None:
            per_page = self.per_page
        if limit is None:
            limit = self.limit or len(iterable)

        if per_page is not None:
            start = page * per_page
            end = min((page + 1) * per_page, limit)

        else:
            start = 0
            end = limit

        return itertools.islice(iterable, start, end)


@dataclass
class SearchRequest(PagingMixin, Coll.Search):
    """Request model for paper search."""

    # TODO: hide the format field from the api entry point schema
    format: int = None

    # Disable format
    def format(self, *args, **kwargs):
        pass


@dataclass
class SearchResponse:
    """Response model for paper search."""

    papers: List[Paper]
    total: int


@dataclass
class LocateFulltextRequest(PagingMixin, Fulltext.Locate):
    """Request model for fulltext locate."""

    # Disable format
    def format(self, *args, **kwargs):
        pass


@dataclass
class LocateFulltextResponse:
    """Response model for fulltext locate."""

    urls: list[URL]


@dataclass
class DownloadFulltextRequest(Fulltext.Download):
    """Request model for fulltext download."""

    ref: str | list[str]

    # Disable format
    def format(self, *args, **kwargs):
        pass

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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
        root_path="/api/v1",
    )

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": app.title,
            "version": app.version,
        }

    @app.get("/search", response_model=SearchResponse)
    async def search_papers(request: SearchRequest = None):
        """Search for papers in the collection."""
        request = request or SearchRequest()
        coll = Coll(command=None)

        try:
            # Perform search using the collection's search method
            results = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(request.slice(request.run(coll)))
            )

            return SearchResponse(papers=results, total=len(coll.collection))

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    @app.get("/fulltext/locate")
    async def locate_fulltext(request: LocateFulltextRequest):
        """Locate fulltext urls for a paper."""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(request.slice(request.run()))
            )
            return LocateFulltextResponse(urls=results)

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Locate fulltext failed: {str(e)}"
            )

    @app.get("/fulltext/download")
    async def download_fulltext(request: DownloadFulltextRequest):
        """Download fulltext for a paper."""
        try:
            # Run blocking download in thread pool
            pdf = await asyncio.get_event_loop().run_in_executor(None, request.run)

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

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Download fulltext failed: {str(e)}"
            )

    return app
