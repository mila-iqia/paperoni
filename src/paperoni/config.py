from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property
from pathlib import Path

import gifnoc
import requests_cache
from requests import Session
from serieux import TaggedSubclass

from .discovery.base import Discoverer
from .model.focus import Focuses


@dataclass
class RequesterConfig:
    cache_path: Path = None
    expire_after: timedelta = None

    @cached_property
    def session(self):
        if self.cache_path is None:
            return Session()
        else:
            exp = self.expire_after
            if exp is None:
                exp = requests_cache.NEVER_EXPIRE
            return requests_cache.CachedSession(self.cache_path, expire_after=exp)


@dataclass
class PaperoniConfig:
    cache_path: Path = None
    mailto: str = ""
    requests: RequesterConfig = field(default_factory=RequesterConfig)
    discovery: dict[str, TaggedSubclass[Discoverer]] = field(default_factory=dict)
    focuses: Focuses = field(default_factory=Focuses)


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

requests = gifnoc.proxy("paperoni.requests.session")
discoverers = gifnoc.proxy("paperoni.discovery")
