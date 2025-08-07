import hashlib
import shutil
from dataclasses import dataclass

from serieux import dump, load

from ..config import config
from .locate import URL, locate_all


@dataclass
class CachePolicy:
    use: bool = True
    download: bool = True
    best: bool = False


class CachePolicies:
    USE = CachePolicy(use=True, download=True, best=False)
    USE_BEST = CachePolicy(use=True, download=True, best=True)
    NO_DOWNLOAD = CachePolicy(use=True, download=False, best=False)
    FORCE = CachePolicy(use=False, download=True, best=True)


@dataclass
class ErrorData:
    type: str
    message: str


@dataclass
class Info:
    id: str = None
    title: str = None
    ref: str = None


@dataclass
class PDF:
    source: URL
    hash: str = None
    info: Info = None
    success: bool = False
    error: ErrorData = None

    def __post_init__(self):
        if self.hash is None:
            self.hash = hashlib.sha256(str(self.source).encode()).hexdigest()
        self.directory = (config.data_path / "pdf" / self.hash).resolve()
        self.meta_path = self.directory / "meta.yaml"
        self.pdf_path = self.directory / "fulltext.pdf"

    def ensure(self):
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self):
        if self.meta_path.exists():
            return load(PDF, self.meta_path)
        else:
            return self

    def dump(self):
        self.ensure()
        dump(PDF, self, dest=self.meta_path)

    def clear(self):
        assert self.directory.is_relative_to(config.data_path.resolve())
        shutil.rmtree(self.directory, ignore_errors=True)

    def fetch(self):
        self.ensure()
        try:
            config.fetch.download(
                url=self.source.url,
                filename=self.pdf_path,
            )
            if not self.pdf_path.exists() or not self.pdf_path.is_file():
                raise Exception(f"Downloaded file does not exist: {self.pdf_path}")
            with open(self.pdf_path, "rb") as f:
                header = f.read(5)
                if header != b"%PDF-":
                    raise Exception(
                        f"File at {self.pdf_path} is not a valid PDF (missing %PDF- header)"
                    )
            self.success = True
            return self.pdf_path
        except Exception as exc:
            self.error = ErrorData(
                type=type(exc).__name__,
                message=str(exc),
            )
            self.success = False
            raise
        finally:
            self.dump()

    def fulltext(self, cache_policy: CachePolicy = CachePolicies.USE):
        if not cache_policy.use or not self.success or not self.pdf_path.exists():
            if not cache_policy.download:
                raise Exception(
                    f"No PDF for {self.source.url} and cache policy prevents downloading"
                )
            return self.fetch()
        else:
            return self.pdf_path


def get_pdf(refs, cache_policy: CachePolicy = CachePolicies.USE):
    if isinstance(refs, str):
        refs = [refs]

    if cache_policy.use and not cache_policy.best:
        urls = [url for ref in refs for url in locate_all(ref)]
        for url in urls:
            if (p := PDF(url).load()).success:
                return p

    exceptions = []
    for ref in refs:
        for url in locate_all(ref):
            p = PDF(url).load()
            try:
                p.fulltext(cache_policy=cache_policy)
                return p
            except Exception as exc:
                exceptions.append(exc)
                continue

    raise ExceptionGroup("No fulltext found for any reference", exceptions)
