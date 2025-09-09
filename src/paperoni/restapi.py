"""
FastAPI interface for paperoni collection search functionality.
"""

import importlib.metadata
import itertools
from dataclasses import dataclass
from typing import Iterable, List

from fastapi import FastAPI, HTTPException

import paperoni
from paperoni.__main__ import Coll

from .collection.abc import PaperCollection
from .model.classes import Paper


@dataclass
class PagingMixin:
    """Mixin for paging."""

    # Page of results to display
    page: int = None
    # Number of results to display per page
    per_page: int = None
    # Max number of papers to show
    limit: int = None

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
class SearchRequest(Coll.Search, PagingMixin):
    """Request model for paper search."""

    limit: int = 100


@dataclass
class SearchResponse:
    """Response model for paper search."""

    papers: List[Paper]
    total: int


def create_app(collection: PaperCollection) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
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
        try:
            # Perform search using the collection's search method
            results = list(
                request.slice(
                    collection.search(
                        title=request.title,
                        author=request.author,
                        institution=request.institution,
                    )
                )
            )

            return SearchResponse(papers=results, total=len(collection))

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app
