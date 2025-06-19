from dataclasses import dataclass
from pathlib import Path

import gifnoc
from serieux import TaggedSubclass

from .discovery.base import Discoverer


@dataclass
class PaperoniConfig:
    cache_path: Path = None


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

discoverers = gifnoc.define(
    "paperoni.discovery",
    dict[str, TaggedSubclass[Discoverer]],
)
