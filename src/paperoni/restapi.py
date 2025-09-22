"""
FastAPI interface for paperoni collection search functionality.
"""

import datetime
import hashlib
import importlib.metadata
import itertools
from dataclasses import dataclass
from typing import Iterable

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from serieux import dump, serialize

import paperoni

from .__main__ import Coll, Fulltext, Work
from .config import config
from .fulltext.locate import URL
from .model.classes import Paper
from .model.focus import Focuses, Scored
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


# Authentication models
@dataclass
class User:
    """User model for authentication."""

    email: str
    name: str = None
    admin: bool = False

    def user_id(self) -> str:
        """Get user id."""
        email_hash = hashlib.sha256(self.email.encode()).hexdigest()
        return f"{self.email.split('@')[0]}_{email_hash[:8]}"


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

    papers: list[Paper]
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


@dataclass
class IncludeRequest(Work.Include):
    """Request model for work state paper include."""


@dataclass
class IncludeResponse:
    """Response model for work state paper include."""

    total: int


@dataclass
class ViewRequest(PagingMixin, Work.View):
    """Request model for work state paper view."""

    # Disable format
    format: int = None

    def __post_init__(self):
        self.n = self.n or self.limit
        self.limit = min(self.limit, self.n)

    def format(self, *args, **kwargs):
        pass


@dataclass
class ViewResponse:
    """Response model for work state paper view."""

    papers: list[Scored[Paper]]
    total: int


@dataclass
class LoginRequest:
    """Request model for login."""

    email: str = None


@dataclass
class LoginResponse:
    """Response model for login."""

    access_token: str


# Authentication dependencies
async def get_current_user(request: LoginResponse):
    """Get current user from token."""
    try:
        payload = jwt.decode(
            request.access_token, config.server.secret_key, algorithms=["HS256"]
        )
        user = User(**payload["user"])
    except jwt.exceptions.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if user.email is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user


async def get_current_admin(request: LoginResponse):
    """Get current admin from token."""
    user = await get_current_user(request)

    if not user.admin:
        raise HTTPException(status_code=401, detail="Permission denied")

    return user


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
        root_path="/api/v1",
    )

    focus_file = config.server.client_dir / "focuses.yaml"

    if not focus_file.exists():
        focus_file.parent.mkdir(exist_ok=True, parents=True)
        dump(Focuses, config.focuses, dest=focus_file)

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": app.title,
            "version": app.version,
        }

    @app.get("/auth", response_model=LoginResponse)
    async def auth(request: LoginRequest):
        """Login with email and access token."""
        # Compute new access token
        user = User(email=request.email, name=None)
        payload = {
            "user": serialize(User, user),
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=28),
        }
        access_token = jwt.encode(payload, config.server.secret_key, algorithm="HS256")
        return LoginResponse(access_token=access_token)

    @app.get(
        "/search",
        response_model=SearchResponse,
        dependencies=[Depends(get_current_user)],
    )
    async def search_papers(request: SearchRequest = None):
        """Search for papers in the collection."""
        request = request or SearchRequest()
        coll = Coll(command=None)

        try:
            # Perform search using the collection's search method
            results = list(request.slice(request.run(coll)))

            return SearchResponse(papers=results, total=len(coll.collection))

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    @app.get(
        "/work/view",
        response_model=ViewResponse,
        dependencies=[Depends(get_current_user)],
    )
    async def work_view_papers(
        request: ViewRequest = None, user: User = Depends(get_current_user)
    ):
        """Search for papers in the collection."""
        request = request or ViewRequest()

        work_file = config.server.client_dir / user.user_id() / "work.yaml"

        work = Work(command=None, work_file=work_file, focus_file=focus_file)

        try:
            papers: list[Scored[Paper]] = list(request.slice(request.run(work)))

            return ViewResponse(
                papers=serialize(list[Scored[Paper]], papers), total=len(papers)
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"View failed: {str(e)}")

    @app.get(
        "/work/include",
        response_model=IncludeResponse,
        dependencies=[Depends(get_current_admin)],
    )
    async def work_include_papers(
        request: IncludeRequest = None, user: User = Depends(get_current_admin)
    ):
        """Search for papers in the collection."""
        request = request or IncludeRequest()

        work_file = config.server.client_dir / user.user_id() / "work.yaml"

        work = Work(command=None, work_file=work_file, focus_file=focus_file)

        try:
            # Perform search using the collection's search method
            added = request.run(work)

            return IncludeResponse(total=added)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Include failed: {str(e)}")

    @app.get("/fulltext/locate", dependencies=[Depends(get_current_user)])
    async def locate_fulltext(request: LocateFulltextRequest):
        """Locate fulltext urls for a paper."""
        try:
            urls = list(request.slice(request.run()))
            return LocateFulltextResponse(urls=urls)

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Locate fulltext failed: {str(e)}"
            )

    @app.get("/fulltext/download", dependencies=[Depends(get_current_user)])
    async def download_fulltext(request: DownloadFulltextRequest):
        """Download fulltext for a paper."""
        try:
            # Run blocking download in thread pool
            pdf = request.run()

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
