from dataclasses import dataclass, field
from pathlib import Path

import gifnoc
from serieux import TaggedSubclass
from serieux.features.encrypt import Secret

from .collection.abc import PaperCollection
from .get import Fetcher, RequestsFetcher
from .model.focus import AutoFocus, Focuses
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
    api_keys: Keys[str, Secret[str]] = field(default_factory=Keys)
    fetch: TaggedSubclass[Fetcher] = field(default_factory=RequestsFetcher)
    focuses: Focuses = field(default_factory=Focuses)
    autofocus: AutoFocus[str, AutoFocus.Type] = field(default_factory=AutoFocus)
    refine: Refine = None
    work_file: Path = None
    collection: TaggedSubclass[PaperCollection] = None

    def __post_init__(self):
        # Only used for type hinting
        self._file: Path = getattr(self, "_file", None)
        # Ideally we would not need this but there seams to an issue with
        # autofocus not being of type AutoFocus when using something like:
        # with gifnoc.overlay(
        #         {
        #             "paperoni.autofocus": {
        #                 "author": {"score": 1, "threshold": 5},
        #                 "institution": {"score": 5, "threshold": 20},
        #             },
        #         }
        #     ):
        self.autofocus = AutoFocus(**self.autofocus)

    # TODO: Why does this seams to disable future gifnoc.define like
    # `paperoni.semantic_scholar`?
    # gifnoc.proxy.MissingConfigurationError: No configuration was found for 'paperoni.semantic_scholar'
    # @classmethod
    # def serieux_deserialize(cls, obj, ctx, call_next):
    #     deserialized: PaperoniConfig = call_next(cls, obj, ctx)
    #     if isinstance(ctx.full_path, Path):
    #         config_file: Path = ctx.full_path
    #     elif config_file := os.environ.get("GIFNOC_FILE", None):
    #         config_file: Path = Path(os.environ.get("GIFNOC_FILE"))
    #     if config_file:
    #         deserialized._file = config_file
    #     return deserialized


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

gifnoc_model = gifnoc.global_registry.model()
