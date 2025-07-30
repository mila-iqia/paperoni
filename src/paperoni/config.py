from dataclasses import dataclass, field
from pathlib import Path

import gifnoc
from serieux import TaggedSubclass

from .discovery.base import Discoverer
from .get import Fetcher, RequestsFetcher
from .model.focus import Focuses


@dataclass
class PaperoniConfig:
    cache_path: Path = None
    mailto: str = ""
    fetch: TaggedSubclass[Fetcher] = field(default_factory=RequestsFetcher)
    discovery: dict[str, TaggedSubclass[Discoverer]] = field(default_factory=dict)
    focuses: Focuses = field(default_factory=Focuses)


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

type JSON = dict[str, JSON] | list[JSON] | int | str | bool | type(None)
gifnoc.define("secrets", JSON)

requests = gifnoc.proxy("paperoni.requests.session")
discoverers = gifnoc.proxy("paperoni.discovery")
