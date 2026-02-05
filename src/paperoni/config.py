from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from tempfile import NamedTemporaryFile
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
class SSLConfig:
    enabled: bool = True
    cert: str
    key: Secret[str]

    @cached_property
    def cert_file(self):
        with NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as cf:
            cf.write(self.cert)
            return cf.name

    @cached_property
    def key_file(self):
        with NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as kf:
            kf.write(self.key)
            return kf.name


@dataclass(kw_only=True)
class Server:
    host: str = "localhost"
    external_host: str = None
    port: int = 8000
    protocol: Literal["http", "https"] = "http"
    max_results: int = 10000
    auth: OAuthManager = None
    assets: Path = None
    ssl: SSLConfig = None

    def __post_init__(self):
        if self.external_host is None:
            self.external_host = f"{self.protocol}://{self.host}"
            if self.port not in (80, 443):
                self.external_host += f":{self.port}"


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
    autovalidation_threshold: float = 10.0

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

    class SerieuxConfig:
        allow_extras = True


config = gifnoc.define(
    "paperoni",
    PaperoniConfig,
)

gifnoc_model = gifnoc.global_registry.model()
