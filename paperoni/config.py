from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Union

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
        self.__dict__.update(ns.__dict__)
        self._database = None
        self._history_file = None

    def install(self):
        if rq := getattr(self.paths, "requests_cache", None):
            import requests_cache

            requests_cache.install_cache(rq)

    def uninstall(self):
        if getattr(self.paths, "requests_cache", None):
            import requests_cache

            requests_cache.uninstall_cache()

    @property
    def database(self):
        if self._database is None:
            from .db.database import Database

            self._database = Database(self.paths.database)
        return self._database

    @property
    def history_file(self):
        if self._history_file is None:
            hroot = self.paths.history
            hroot.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d-%s")
            tag = getattr(self, "tag", "")
            tag = tag and f"-{tag}"
            hfile = hroot / f"{now}{tag}.jsonl"
            self._history_file = hfile
        return self._history_file


@contextmanager
def load_config(config_path, **extra):
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
