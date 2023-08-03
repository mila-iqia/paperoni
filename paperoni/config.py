from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Union

import requests_cache
from coleo import config as configuration
from ovld import ovld

config = ContextVar("paperoni_config")


@ovld
def make_configuration(self, config_dir: Path, keyname: str, d: dict):
    match keyname:
        case "paths":
            return SimpleNamespace(
                **{k: self(config_dir, k, Path(v)) for k, v in d.items()}
            )
        case _:
            return SimpleNamespace(
                **{k: self(config_dir, k, v) for k, v in d.items()}
            )


@ovld
def make_configuration(self, config_dir: Path, keyname: str, p: Path):
    p = p.expanduser()
    if not p.is_absolute():
        p = config_dir / p
    return p


@ovld
def make_configuration(self, config_dir: Path, keyname: str, o: object):
    return o


@ovld
def make_configuration(self, config_path: Union[str, Path]):
    config_path = Path(config_path).expanduser().absolute()
    x = configuration(str(config_path))
    return Configuration(self(config_path.parent, "", x))


class Configuration:
    def __init__(self, ns):
        self.tokens = {}
        self.tweaks = {}
        self.__dict__.update(ns.__dict__)
        self._database = None
        self._history_file = None

    @contextmanager
    def permanent_request_cache(self):
        if rq := getattr(self.paths, "permanent_requests_cache", None):
            # enabled() cannot be nested with itself (which we may want to do to
            # use different parameters in each call), but with disabled()
            # in-between, the finalization of disabled() will put back the
            # previous session cache, so it's a kind of workaround
            with requests_cache.disabled():
                with requests_cache.enabled(rq):
                    yield
        else:
            yield

    def install(self):
        """Set up relevant features globally, as defined in this config.

        * Import requests_cache and set up with cache path ``paths.requests_cache``.
        """
        if rq := getattr(self.paths, "requests_cache", None):
            requests_cache.install_cache(rq, expire_after=timedelta(days=6))

    def uninstall(self):
        """Undo what has been done in self.install().

        * Disable requests_cache.
        """
        if getattr(self.paths, "requests_cache", None):
            requests_cache.uninstall_cache()

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
            tag = getattr(self, "tag", "")
            tag = tag and f"-{tag}"
            hfile = hroot / f"{now}{tag}.jsonl"
            self._history_file = hfile
        return self._history_file

    def get_token(self, service):
        return getattr(self.tokens, service, None)


@contextmanager
def load_config(config_path: str | Path, **extra) -> Configuration:
    """Load the configuration located at the given path.

    Any path defined in the configuration file is relative to the
    configuration file's parent directory.

    Arguments:
        config_path: Path to the configuration
        extras: Key/value pairs to set in the config (overrides it)
    """
    config_path = Path(config_path).expanduser().absolute()
    x = configuration(str(config_path))
    x.update(extra)
    c = Configuration(make_configuration(config_path.parent, "", x))
    c.install()
    token = config.set(c)

    try:
        yield c
    finally:
        config.reset(token)
        c.uninstall()


def get_config():
    return config.get()
