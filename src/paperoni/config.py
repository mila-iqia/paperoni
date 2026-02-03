from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import gifnoc
from easy_oauth import OAuthManager
from rapporteur.report import Reporter
from serieux import TaggedSubclass
from serieux.features.encrypt import Secret
from serieux.features.filebacked import FileProxy

from .collection.abc import PaperCollection
from .get import Fetcher, RequestsFetcher
from .model.focus import AutoFocus, Focuses
from .prompt import GenAIPrompt, Prompt


class Keys(dict):
    def __getattr__(self, attr):
        return self.get(attr, None)


class Meta[T](Keys[str, T]):
    def __getattr__(self, attr) -> T:
        return self.get(attr, None)

    def __setattr__(self, attr, value) -> T:
        self[attr] = value
        return value


@dataclass
class Refine:
    prompt: TaggedSubclass[Prompt] = field(default_factory=GenAIPrompt)


@dataclass(kw_only=True)
class Server:
    host: str = "localhost"
    port: int = 8000
    protocol: Literal["http", "https"] = "http"
    max_results: int = 10000
    process_pool_executor: dict = field(default_factory=dict)
    auth: OAuthManager = None
    assets: Path = None

    def __post_init__(self):
        if self.process_pool_executor.get("max_workers", 0) == 0:
            self.process_pool = None
        else:
            self.process_pool = ProcessPoolExecutor(**self.process_pool_executor)


@dataclass
class AutoValidate:
    score_threshold: float = 10.0


@dataclass
class PaperoniConfig:
    cache_path: Path = None
    data_path: Path = None
    mailto: str = ""
    api_keys: Keys[str, Secret[str]] = field(default_factory=Keys)
    fetch: TaggedSubclass[Fetcher] = field(default_factory=RequestsFetcher)
    focuses: Focuses @ FileProxy(refresh=True) = field(default_factory=Focuses)
    autofocus: AutoFocus = field(default_factory=AutoFocus)
    autovalidate: AutoValidate = field(default_factory=AutoValidate)
    refine: Refine = None
    work_file: Path = None
    collection: TaggedSubclass[PaperCollection] = None
    reporters: list[TaggedSubclass[Reporter]] = field(default_factory=list)
    server: Server = field(default_factory=Server)

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
