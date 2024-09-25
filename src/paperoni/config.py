from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import gifnoc
import requests_cache
from gifnoc import Extensible


@dataclass
class PaperoniPaths:
    database: Path = None
    history: Path = None
    cache: Path = None
    fulltext: Path = None
    requests_cache: Path = None
    permanent_requests_cache: Path = None


@dataclass
class PaperoniTokens:
    semantic_scholar: str = None
    xplore: str = None
    elsevier: str = None
    springer: str = None
    zeta_alpha: str = None
    wiley: str = None


@dataclass
class PaperoniTweaks:
    low_confidence_authors: list[str]


@dataclass
class InstitutionPattern:
    pattern: str
    category: str


@dataclass
class ServiceConfig:
    enabled: bool


@dataclass
class PaperoniConfig:
    paths: PaperoniPaths
    tag: str = None
    tokens: PaperoniTokens = None
    tweaks: PaperoniTweaks = None
    institution_patterns: list[InstitutionPattern] = None
    history_tag: str | None = None
    services: dict[str, ServiceConfig] = None
    writable: bool = True
    # Optional email to use for polite pool in scrapers (e.g. in OpenAlex)
    mailto: str | None = None

    def __post_init__(self):
        self._database = None
        self._history_file = None

    @property
    def database(self):
        """Load the database from ``paths.database`` (lazily)."""
        if self._database is None:
            from .db.database import Database

            self._database = Database(self.paths.database)
        return self._database

    @property
    def history_file(self):
        """Return the history file to use.

        The history file is located in the ``paths.history`` directory and
        is a function of the time and the ``tag`` configuration parameter.
        """
        if self._history_file is None:
            hroot = self.paths.history
            hroot.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d-%s")
            tag = self.history_tag and f"-{self.history_tag}"
            hfile = hroot / f"{now}{tag}.jsonl"
            self._history_file = hfile
        return self._history_file

    @contextmanager
    def permanent_request_cache(self):
        if rq := self.paths.permanent_requests_cache:
            # enabled() cannot be nested with itself (which we may want to do to
            # use different parameters in each call), but with disabled()
            # in-between, the finalization of disabled() will put back the
            # previous session cache, so it's a kind of workaround
            with requests_cache.disabled():
                with requests_cache.enabled(rq):
                    yield
        else:
            yield

    def get_token(self, service):
        return getattr(self.tokens, service, None)

    def __enter__(self):
        """Set up relevant features globally, as defined in this config.

        * Import requests_cache and set up with cache path ``paths.requests_cache``.
        """
        if rq := self.paths.requests_cache:
            requests_cache.install_cache(rq, expire_after=timedelta(days=6))

    def __exit__(self, exct, excv, tb):
        """Undo what has been done in __enter__.

        * Disable requests_cache.
        """
        if self.paths.requests_cache:
            requests_cache.uninstall_cache()


@contextmanager
def load_config(*sources, tag=None):
    """Load the configuration located at the given path.

    Any path defined in the configuration file is relative to the
    configuration file's parent directory.

    Arguments:
        config_path: Path to the configuration
        extras: Key/value pairs to set in the config (overrides it)
    """
    override = {"paperoni": {"history_tag": tag}} if tag else {}

    with gifnoc.overlay(*sources, override) as gcfg:
        yield gcfg.paperoni


papconf = gifnoc.define(
    field="paperoni",
    model=Extensible[PaperoniConfig],
)
