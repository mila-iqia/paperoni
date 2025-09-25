"""
FastAPI interface for paperoni collection search functionality.
"""

import asyncio
import datetime
import enum
import hashlib
import importlib.metadata
import itertools
import secrets
import urllib.parse
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Literal, Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from serieux import deserialize, dump, serialize
from starlette.middleware.sessions import SessionMiddleware

import paperoni

from .__main__ import Coll, Focus, Fulltext, Work
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

    @property
    def is_admin(self) -> bool:
        """Get user id."""
        return self.email in config.server.admin_emails

    def user_id(self) -> str:
        """Get user id."""
        email_hash = hashlib.sha256(self.email.encode()).hexdigest()
        return f"{self.email.split('@')[0]}_{email_hash[:8]}"


@dataclass
class AuthorizedUser(User):
    """Response model for authentication."""

    access_token: str = None


@dataclass
class SearchRequest(PagingMixin, Coll.Search):
    """Request model for paper search."""

    # TODO: hide the format field from the api endpoint schema
    format: int = field(init=False, repr=False, compare=False, default=None)

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

    what: Literal["paper"] = field(init=False, repr=False, compare=False, default="paper")

    # TODO: hide the format field from the api endpoint schema
    format: int = field(init=False, repr=False, compare=False, default=None)

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
class AutoFocusRequest(Focus.AutoFocus):
    """Request model for autofocus."""

    pass


@dataclass
class LoginResponse:
    """Response model for login."""

    headless_url: str
    token_url: str


@dataclass
class AuthResponse(AuthorizedUser):
    """Response model for authentication."""

    pass


# Security scheme for API documentation
security = HTTPBearer(auto_error=False)


# Authentication dependencies
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
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
        return deserialize(User, user)

    raise HTTPException(status_code=401, detail="Authentication required")


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Get current admin user."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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

    @enum.unique
    class HeadlessLoginFlag(enum.Enum):
        ACTIVE = "active"

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
        except Exception:
            raise HTTPException(status_code=401, detail="Google authentication failed.")

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

        try:
            # Perform search using the collection's search method
            results = list(request.slice(request.run(coll)))

            return SearchResponse(papers=results, total=len(coll.collection))

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    @app.get(
        "/work/view",
        response_model=ViewResponse,
    )
    async def work_view_papers(
        request: ViewRequest = None, user: User = Depends(get_current_user)
    ):
        """Search for papers in the collection."""
        request = request or ViewRequest()

        work_file = config.server.client_dir / user.user_id() / "work.json"

        work = Work(command=None, work_file=work_file)

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
    )
    async def work_include_papers(
        request: IncludeRequest = None, user: User = Depends(get_current_admin)
    ):
        """Search for papers in the collection."""
        request = request or IncludeRequest()

        work_file = config.server.client_dir / user.user_id() / "work.json"

        work = Work(command=None, work_file=work_file)

        try:
            added = request.run(work)

            return IncludeResponse(total=added)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Include failed: {str(e)}")

    @app.get(
        "/focus/auto",
        response_model=Focuses,
        dependencies=[Depends(get_current_admin)],
    )
    async def autofocus(request: AutoFocusRequest = None):
        """Autofocus the collection."""
        request = request or AutoFocusRequest()
        focus = Focus(command=None, focus_file=focus_file)

        try:
            return request.run(focus)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Autofocus failed: {str(e)}")

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
