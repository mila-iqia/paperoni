"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import datetime
import enum
import hashlib
import importlib.metadata
import itertools
import logging
import secrets
import urllib.parse
from dataclasses import dataclass, field
from functools import cached_property, lru_cache, partial
from types import NoneType
from typing import AsyncGenerator, Generator, Iterable, Literal

from anyio import Path
from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from serieux import auto_singleton, deserialize, serialize
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

import paperoni
from paperoni.fulltext.pdf import PDF

from .__main__ import Coll, Focus, Formatter, Fulltext, Work
from .config import config
from .fulltext.locate import URL
from .model.classes import Paper, PaperInfo
from .model.focus import Focuses, Scored
from .utils import url_to_id

restapi_logger = logging.getLogger(__name__)


@enum.unique
class HeadlessLoginFlag(enum.Enum):
    ACTIVE = "active"


@auto_singleton("raw")
class RawFormatter(Formatter):
    def __call__(self, things):
        yield from things


@dataclass
class PagingMixin:
    """Mixin for paging."""

    # Results offset
    offset: int = field(default=0)
    # Max number of results to return
    size: int = field(default=100)

    _count: NoneType = field(init=False, repr=False, compare=False, default=0)
    _next_offset: NoneType = field(init=False, repr=False, compare=False, default=None)

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

        if self._count < self.size:
            # No more results
            self._next_offset = None


@dataclass
class PagingResponseMixin:
    """Mixin for paging response."""

    results: list
    count: int
    next_offset: int | None
    total: int


# Authentication models
@dataclass(frozen=True)
class User:
    """User model for authentication."""

    email: str
    as_user: bool = False

    @cached_property
    def is_admin(self) -> bool:
        """Get user id."""
        return not self.as_user and self.email in config.server.admin_emails

    @cached_property
    def work_file(self) -> Path:
        """Get user work file."""
        if self.is_admin:
            # Admin user work file is the config file. That file is thus shared
            # by all admins.
            work_file = config.work_file

        else:
            email_hash = hashlib.sha256(self.email.encode()).hexdigest()
            work_file = (
                config.server.client_dir
                / f"{self.email.split('@')[0]}_{email_hash[:8]}"
                / "work.yaml"
            )

        work_file.parent.mkdir(parents=True, exist_ok=True)
        return work_file


@dataclass(frozen=True)
class AuthorizedUser(User):
    """Response model for authentication."""

    access_token: str = None


@dataclass
class SearchRequest(PagingMixin, Coll.Search):
    """Request model for paper search."""

    # TODO: hide the format field from the api endpoint schema
    format: NoneType = field(
        init=False, repr=False, compare=False, default_factory=lambda: RawFormatter
    )

    def __post_init__(self):
        # Type hinting for format
        self.format: RawFormatter = self.format


@dataclass
class SearchResponse(PagingResponseMixin):
    """Response model for paper search."""

    results: list[Paper]


@dataclass
class LocateFulltextRequest(PagingMixin, Fulltext.Locate):
    """Request model for fulltext locate."""

    def format(self, urls: list[URL]):
        yield from RawFormatter(urls)


@dataclass
class LocateFulltextResponse(PagingResponseMixin):
    """Response model for fulltext locate."""

    results: list[URL]


@dataclass
class DownloadFulltextRequest(Fulltext.Download):
    """Request model for fulltext download."""

    ref: str | list[str]
    cache_policy: Literal["no_download"] = field(
        init=False, repr=False, compare=False, default="no_download"
    )

    def format(self, pdf: PDF):
        yield from RawFormatter([pdf])

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

    what: Literal["paper"] = field(init=False, repr=False, compare=False, default="paper")
    n: NoneType = field(init=False, repr=False, compare=False, default=None)

    # TODO: hide the format field from the api endpoint schema
    format: NoneType = field(
        init=False, repr=False, compare=False, default_factory=lambda: RawFormatter
    )

    def __post_init__(self):
        # Type hinting for format
        self.format: RawFormatter = self.format


@dataclass
class AddRequest(Work.Get):
    # disable command
    command: NoneType = field(init=False, repr=False, compare=False, default=None)

    papers: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.user: User = None

    def iterate(self, **kwargs) -> Generator[PaperInfo, None, None]:
        papers = deserialize(list[Paper], self.papers)

        for paper in papers:
            yield PaperInfo(
                key=f"user:{self.user.email}",
                acquired=datetime.datetime.now(datetime.timezone.utc),
                paper=paper,
                info={"added_by": {"user": self.user.email}},
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


@dataclass
class LoginResponse:
    """Response model for login."""

    headless_url: str
    token_url: str


@dataclass(frozen=True)
class AuthResponse(AuthorizedUser):
    """Response model for authentication."""

    as_user: NoneType = field(init=False, repr=False, compare=False, default=False)


# Security scheme for API documentation
security = HTTPBearer(auto_error=False)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
        root_path="/api/v1",
    )
    # Add session middleware for OAuth
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.server.secret_key,
        max_age=14 * 24 * 60 * 60,  # 14 days
    )

    @app.exception_handler(Exception)
    async def exception_handler(request, exc):
        restapi_logger.exception(exc)

        if getattr(exc, "status_code", None) is None:
            exc = HTTPException(status_code=500, detail="Internal Server Error")

        return await http_exception_handler(request, exc)

    @lru_cache(maxsize=100)
    def headless_login(
        state: str,
    ) -> dict[str, asyncio.Event | User | HeadlessLoginFlag]:
        if not state:
            return None

        return {"event": asyncio.Event(), "user": None, "status": None}

    @lru_cache(maxsize=100000)
    def active_logins(work_file: Path) -> asyncio.Lock:
        return asyncio.Lock()

    def check_headless_state(state: str) -> bool:
        return state and headless_login(state)["status"] is not None

    async def get_oauth_state(request: Request, state: str = None) -> str:
        if (
            state
            and jwt.decode(state, config.server.jwt_secret_key, algorithms=["HS256"])[
                "state"
            ]
            and state != request.session.get("oauth_state")
            and not check_headless_state(state)
        ):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        return state or jwt.encode(
            {
                "state": secrets.token_urlsafe(32),
                "exp": datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5),
            },
            config.server.jwt_secret_key,
            algorithm="HS256",
        )

    # OAuth Setup
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=config.server.client_id,
        client_secret=config.server.client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email",
            "prompt": "select_account",  # force to select account
        },
    )

    # Authentication dependencies
    async def get_current_user(
        request: Request,
        as_user: bool = False,
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> AsyncGenerator[User, None]:
        """Get current user from JWT token or session."""
        user = None

        # Try to get user from Authorization header first
        if credentials:
            try:
                user = jwt.decode(
                    credentials.credentials,
                    config.server.jwt_secret_key,
                    algorithms=["HS256"],
                )
            except JWTError:
                pass

        # Try to get user from session
        user = user or request.session.get("user")

        if user:
            user = {**user, "as_user": as_user}
            user = deserialize(User, user)
            yield user

        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    async def acquire_current_user(
        user: User = Depends(get_current_user),
    ) -> AsyncGenerator[User, None]:
        """Acquire current user lock."""
        locked = False
        # As all admins share the same work file, the lock is also shared by all
        # admins.
        lock = active_logins(user.work_file)

        try:
            async with asyncio.timeout(5):
                locked = await lock.acquire()
            yield user

        except TimeoutError:
            raise HTTPException(
                status_code=403,
                detail="User is already logged in and running operations. Please logout from other sessions or wait for the operation to finish and try again.",
            )

        finally:
            if locked:
                lock.release()

    acquire_current_user_as_user = partial(
        acquire_current_user, user=Depends(partial(get_current_user, as_user=True))
    )

    async def acquire_current_admin(
        user: User = Depends(acquire_current_user),
    ) -> AsyncGenerator[User, None]:
        """Get current admin user."""
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        yield user

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": app.title,
            "version": app.version,
        }

    # OAuth Authentication Endpoints
    @app.get("/auth/login", response_model=LoginResponse)
    async def login(
        request: Request,
        headless: bool = False,
        state: str = Depends(get_oauth_state),
    ):
        """Initiate Google OAuth login."""
        # Generate state parameter for CSRF protection
        request.session.clear()

        request.session["oauth_state"] = state

        if headless and not check_headless_state(state):
            url_params = {"headless": headless, "state": state}
            headless_url_params = urllib.parse.urlencode(url_params)
            url_params.pop("headless")
            token_url_params = urllib.parse.urlencode(url_params)

            headless_login(state)["status"] = HeadlessLoginFlag.ACTIVE
            return LoginResponse(
                headless_url=f"{request.url_for('login')}?{headless_url_params}",
                token_url=f"{request.url_for('token')}?{token_url_params}",
            )

        elif headless:
            return await oauth.google.authorize_redirect(
                request,
                request.url_for("auth_headless"),
                state=state,
            )

        else:
            return await oauth.google.authorize_redirect(
                request,
                request.url_for("auth"),
                state=state,
            )

    @app.get("/auth/token", response_model=AuthResponse)
    async def token(state: str = Depends(get_oauth_state)):
        """Handle Google OAuth token."""
        await headless_login(state)["event"].wait()
        user = headless_login(state)["user"]
        headless_login(state)["status"] = None
        return serialize(AuthorizedUser, user)

    @app.get("/auth/headless")
    async def auth_headless(request: Request, state: str = Depends(get_oauth_state)):
        """Handle Google OAuth callback for headless mode."""
        try:
            token = await oauth.google.authorize_access_token(request)

        except OAuthError as e:
            raise HTTPException(
                status_code=401,
                detail=f"[{type(e).__name__}] Google authentication failed: {str(e)}",
            ) from e

        # Create user object
        user = User(email=token["userinfo"]["email"])

        # Store user in session
        request.session["user"] = serialize(User, user)

        # Create token
        payload = {
            **serialize(User, user),
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=14),
        }
        access_token = jwt.encode(
            payload, config.server.jwt_secret_key, algorithm="HS256"
        )

        # Clear OAuth state
        user = AuthorizedUser(**serialize(User, user), access_token=access_token)

        if check_headless_state(state):
            headless_login(state)["user"] = user
            headless_login(state)["event"].set()

        request.session.pop("oauth_state", None)

        return user

    @app.get("/auth")
    async def auth(request: Request, state: str = Depends(get_oauth_state)):
        """Handle Google OAuth callback."""
        user = await auth_headless(request, state)

        # Clear OAuth state
        request.session.pop("oauth_state", None)

        return user

    @app.get(
        "/search",
        response_model=SearchResponse,
        dependencies=[Depends(get_current_user)],
    )
    async def search_papers(request: SearchRequest = None):
        """Search for papers in the collection."""
        request = request or SearchRequest()

        coll = Coll(command=None)

        # Perform search using the collection's search method
        gen = request.run(coll)
        results = list(request.slice(gen))

        return SearchResponse(
            results=results,
            count=request.count,
            next_offset=request.next_offset,
            # Is this wierd to iterate over the whole collection to get the
            # total of matching results?
            total=request.offset + len(results) + len(list(gen)),
        )

    @app.post("/work/add", response_model=AddResponse)
    async def work_add_papers(
        request: AddRequest, user: User = Depends(acquire_current_user_as_user)
    ):
        """Add papers to the user's work."""

        request.user = user

        work = Work(command=None, work_file=user.work_file)
        request.run(work)

        return AddResponse(total=len(work.top))

    @app.get("/work/view", response_model=ViewResponse)
    async def work_view_papers(
        request: ViewRequest = None, user: User = Depends(get_current_user)
    ):
        request = request or ViewRequest()

        """Search for papers in the collection."""
        work = Work(command=None, work_file=user.work_file)

        papers: list[Scored[Paper]] = list(request.slice(request.run(work)))

        return ViewResponse(
            results=serialize(list[Scored[Paper]], papers),
            count=request.count,
            next_offset=request.next_offset,
            total=len(work.top),
        )

    @app.get("/work/include", response_model=IncludeResponse)
    async def work_include_papers(
        request: IncludeRequest, user: User = Depends(acquire_current_user_as_user)
    ):
        """Search for papers in the collection."""
        work = Work(command=None, work_file=user.work_file)

        added = request.run(work)

        return IncludeResponse(total=added)

    @app.get(
        "/focus/auto",
        response_model=Focuses,
        dependencies=[Depends(acquire_current_admin)],
    )
    async def autofocus(request: AutoFocusRequest = None):
        request = request or AutoFocusRequest()

        """Autofocus the collection."""
        focus = Focus(command=None)

        return request.run(focus)

    @app.get(
        "/fulltext/locate",
        response_model=LocateFulltextResponse,
        dependencies=[Depends(get_current_user)],
    )
    async def locate_fulltext(request: LocateFulltextRequest):
        """Locate fulltext urls for a paper."""
        urls = list(request.slice(request.run()))
        return LocateFulltextResponse(
            results=urls,
            count=request.count,
            next_offset=request.next_offset,
            total=len(urls),
        )

    @app.get("/fulltext/download", dependencies=[Depends(get_current_user)])
    async def download_fulltext(request: DownloadFulltextRequest):
        """Download fulltext for a paper."""
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

    return app
