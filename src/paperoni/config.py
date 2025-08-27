from dataclasses import dataclass, field
from pathlib import Path

import gifnoc
from serieux import TaggedSubclass

from .get import Fetcher, RequestsFetcher
from .model.focus import Focuses
from .prompt import GenAIPrompt, Prompt


class Keys(dict):
    def __getattr__(self, attr):
        return self.get(attr, None)


@dataclass
class Refine:
    prompt: TaggedSubclass[Prompt] = field(default_factory=GenAIPrompt)


@dataclass
class PaperoniConfig:
    cache_path: Path = None
    data_path: Path = None
    mailto: str = ""
    api_keys: Keys[str, str] = field(default_factory=Keys)
    fetch: TaggedSubclass[Fetcher] = field(default_factory=RequestsFetcher)
    focuses: Focuses = field(default_factory=Focuses)
    refine: Refine = None


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

type JSON = dict[str, JSON] | list[JSON] | int | str | bool | type(None)
gifnoc.define("secrets", JSON)
