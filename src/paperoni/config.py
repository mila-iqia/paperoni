import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import gifnoc
from easy_oauth import OAuthManager
from rapporteur.report import Reporter
from serieux import JSON, TaggedSubclass
from serieux.features.encrypt import Secret

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
class PaperoniConfig:
    cache_path: Path = None
    data_path: Path = None
    mailto: str = ""
    api_keys: Keys[str, Secret[str]] = field(default_factory=Keys)
    discovery: JSON = None
    fetch: TaggedSubclass[Fetcher] = field(default_factory=RequestsFetcher)
    focuses: Focuses = field(default_factory=Focuses)
    autofocus: AutoFocus[str, AutoFocus.Author] = field(default_factory=AutoFocus)
    refine: Refine = None
    work_file: Path = None
    collection: TaggedSubclass[PaperCollection] = None
    reporters: list[TaggedSubclass[Reporter]] = field(default_factory=list)
    server: Server = field(default_factory=Server)

    def __post_init__(self):
        self.metadata: Meta[Path | list[Path] | Meta | Any] = Meta()

        g_file = os.environ.get("GIFNOC_FILE", None)
        g_file = (g_file and g_file.split(",")) or []
        m_files = self.metadata.files or g_file
        self.metadata.files = [Path(f).resolve() for f in m_files]
        self.metadata.file = (self.metadata.files and self.metadata.files[0]) or None

        self.metadata.focuses = Meta()

        # The focuses and autofocuses files should probably always be relative
        # to the config file and use focuses.yaml and autofocuses.yaml as names.
        if self.metadata.file and self.metadata.file.exists():
            self.metadata.focuses.file = self.metadata.file.parent / "focuses.yaml"
            self.metadata.focuses.autofile = Path(self.metadata.focuses.file).with_stem(
                f"auto{self.metadata.focuses.file.stem}"
            )

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
