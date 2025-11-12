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


# Authentication models
@dataclass(frozen=True)
class User:
    """User model for authentication."""

    email: str
    as_user: bool = False

    class SerieuxConfig:
        allow_extras = True

    @cached_property
    def roles(self) -> set[str]:
        return config.server.user_roles.get(self.email, set())

    @cached_property
    def is_admin(self) -> bool:
        """Get user id."""
        return not self.as_user and "admin" in self.roles

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
    """Response model for headless login."""

    login_url: str
    token_url: str


@dataclass(frozen=True)
class AuthResponse(AuthorizedUser):
    """Response model for authentication."""

    as_user: NoneType = field(init=False, repr=False, compare=False, default=False)


# Security scheme for API documentation
security = HTTPBearer(auto_error=False)


def _search(request: dict):
    request: SearchRequest = deserialize(SearchRequest, request)

    coll = Coll(command=None)

    # Perform search using the collection's search method
    all_matches = request.run(coll)
    results = list(request.slice(all_matches))

    return results, request.count, request.next_offset, len(all_matches)


def _work_view(request: dict, user: User):
    request: ViewRequest = deserialize(ViewRequest, request)

    """Search for papers in the collection."""
    work = Work(command=request, work_file=user.work_file)

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


def add_auth(app):
    # Add session middleware for OAuth
    app.add_middleware(
        SessionMiddleware,
        # NOTE: The `secret_key` should be at least 32 bytes long.
        secret_key=config.server.secret_key,
        max_age=14 * 24 * 60 * 60,  # 14 days
    )

    @lru_cache(maxsize=100)
    def headless_login(
        state: str,
    ) -> dict[str, asyncio.Event | User | HeadlessLoginFlag]:
        if not state:
            return None

        return {"event": asyncio.Event(), "user": None, "status": None}

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
    def user_with_role(role=None):
        async def get_user(
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
                if role is None or role in user.roles:
                    yield user
                else:
                    raise HTTPException(status_code=403, detail=f"{role} role required")
            else:
                raise HTTPException(status_code=401, detail="Authentication required")

        return get_user

    def is_headless(request: Request, headless: bool = False) -> bool:
        """Detect if request should use headless mode based on User-Agent.

        Returns True for CLI tools (curl, wget, etc.) and False for browsers.
        If explicit_headless is provided, it takes precedence.
        """
        user_agent = request.headers.get("user-agent", "").lower()

        # Common browser identifiers
        browser_indicators = [
            "mozilla",
            "chrome",
            "firefox",
            "safari",
            "edge",
            "opera",
            "webkit",
            "gecko",
        ]

        return headless or not any(
            indicator in user_agent for indicator in browser_indicators
        )

    # OAuth Authentication Endpoints
    @app.get("/auth/login", response_model=LoginResponse)
    async def login(
        request: Request,
        headless: bool = Depends(is_headless),
        state: str = Depends(get_oauth_state),
    ):
        """Initiate Google OAuth login.

        The headless parameter can be explicitly set, or it will be automatically
        detected based on the User-Agent header:
        - Browser User-Agents (Firefox, Chrome, Safari, etc.) -> headless=False
        """
        # Generate state parameter for CSRF protection
        request.session.clear()

        request.session["oauth_state"] = state

        # As the session must survive through the whole redirection process
        # (/auth/login -> google oauth -> /auth) to avoid a CSRF protection
        # error, a url containing the state parameter is generated to start a
        # new session when open in the browser which will survive the whole
        # redirection process.
        if headless and not check_headless_state(state):
            url_params = {"headless": headless, "state": state}
            headless_url_params = urllib.parse.urlencode(url_params)
            url_params.pop("headless")
            token_url_params = urllib.parse.urlencode(url_params)

            headless_login(state)["status"] = HeadlessLoginFlag.ACTIVE
            return LoginResponse(
                login_url=f"{request.url_for('login')}?{headless_url_params}",
                token_url=f"{request.url_for('token')}?{token_url_params}",
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

    @app.get("/auth")
    async def auth(request: Request, state: str = Depends(get_oauth_state)):
        """Handle Google OAuth callback."""
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
            payload,
            # NOTE: The `jwt_secret_key` should be at least 32 bytes long.
            config.server.jwt_secret_key,
            algorithm="HS256",
        )

        # Clear OAuth state
        user = AuthorizedUser(**serialize(User, user), access_token=access_token)

        if check_headless_state(state):
            headless_login(state)["user"] = user
            headless_login(state)["event"].set()

        # Clear OAuth state
        request.session.pop("oauth_state", None)

        return user

    return user_with_role


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paperoni API",
        description="API for searching scientific papers",
        version=importlib.metadata.version(paperoni.__name__),
        root_path="/api/v1",
    )

    @app.exception_handler(Exception)
    async def exception_handler(request, exc):
        restapi_logger.exception(exc)

        if getattr(exc, "status_code", None) is None:
            exc = HTTPException(status_code=500, detail="Internal Server Error")

        return await http_exception_handler(request, exc)

    user_with_role = add_auth(app)

    get_current_user = user_with_role()
    get_current_admin = user_with_role("admin")
    get_current_user_as_user = partial(get_current_user, as_user=True)

    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": app.title,
            "version": app.version,
        }

    @app.get(
        "/search",
        response_model=SearchResponse,
        dependencies=[Depends(get_current_user)],
    )
    async def search_papers(request: SearchRequest = Depends()):
        """Search for papers in the collection."""
        results, count, next_offset, total = await run_in_process_pool(
            _search, serialize(SearchRequest, request)
        )
        return SearchResponse(
            results=results, count=count, next_offset=next_offset, total=total
        )

    @app.post("/work/add", response_model=AddResponse)
    async def work_add_papers(
        request: AddRequest, user: User = Depends(get_current_user_as_user)
    ):
        """Add papers to the user's work."""

        request.user = user

        work = Work(command=request, work_file=user.work_file)
        work.run()

        return AddResponse(total=len(work.top))

    @app.get("/work/view", response_model=ViewResponse)
    async def work_view_papers(
        request: ViewRequest = Depends(), user: User = Depends(get_current_user)
    ):
        papers, count, next_offset, total = await run_in_process_pool(
            _work_view, serialize(ViewRequest, request), user
        )
        return ViewResponse(
            results=serialize(list[Scored[Paper]], papers),
            count=count,
            next_offset=next_offset,
            total=total,
        )

    @app.get("/work/include", response_model=IncludeResponse)
    async def work_include_papers(
        request: IncludeRequest, user: User = Depends(get_current_user_as_user)
    ):
        """Search for papers in the collection."""
        work = Work(command=request, work_file=user.work_file)

        added = work.run()

        return IncludeResponse(total=added)

    @app.get(
        "/focus/auto",
        response_model=Focuses,
        dependencies=[Depends(get_current_admin)],
    )
    async def autofocus(request: AutoFocusRequest = Depends()):
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
        results, count, next_offset, total = await run_in_process_pool(
            _locate_fulltext, serialize(LocateFulltextRequest, request)
        )
        return LocateFulltextResponse(
            results=results,
            count=count,
            next_offset=next_offset,
            total=total,
        )

    @app.get("/fulltext/download", dependencies=[Depends(get_current_user)])
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
