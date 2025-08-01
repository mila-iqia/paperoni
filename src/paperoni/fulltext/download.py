import hashlib
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

import yaml
from ovld import ovld
from serieux import deserialize, serialize

from ..config import config
from ..model.classes import PaperInfo
from .locate import URL, locate_all


@dataclass
class CachePolicy:
    use: bool = True
    download: bool = True
    refresh_on_new_links: bool = False

    def __post_init__(self):
        if self.refresh_on_new_links:
            raise Exception("refresh_on_new_links is not supported yet")


class CachePolicies:
    USE = CachePolicy(use=True, download=True, refresh_on_new_links=False)
    NO_DOWNLOAD = CachePolicy(use=True, download=False, refresh_on_new_links=False)
    FORCE = CachePolicy(use=False, download=True, refresh_on_new_links=False)


@dataclass
class ErrorData:
    type: str
    message: str


@dataclass
class DownloadResult:
    ref: str
    url: URL
    downloaded: bool = False
    error: Optional[ErrorData] = None


@dataclass
class Metadata:
    identifier: str
    title: str
    success: bool
    sources: list[DownloadResult]


class PDF:
    def __init__(
        self, identifier: str, title: str, ref: str, cache_policy=CachePolicies.USE
    ):
        self.identifier = identifier
        self.title = title
        self.ref = ref
        self.cache_policy = cache_policy

        # Set paths
        ref_split = self.ref.split(":")
        ref_split[1] = hashlib.sha256(ref_split[1].encode()).hexdigest()
        self.directory = (
            config.data_path / self.identifier.replace(":", "_") / "_".join(ref_split)
        )
        self.meta_path = self.directory / "meta.yaml"
        self.pdf_path = self.directory / "fulltext.pdf"
        if self.meta_path.exists():
            try:
                self.meta = deserialize(
                    Metadata, yaml.safe_load(self.meta_path.read_text())
                )
            except Exception as exc:
                traceback.print_exception(exc)
                self.initialize_meta()
        else:
            self.initialize_meta()

    def initialize_meta(self):
        self.meta = Metadata(
            identifier=self.identifier,
            title=self.title,
            success=False,
            sources=[],
        )

    @ovld
    def make_error(self, ctx, exc: Exception):
        return self.make_error(ctx, type(exc).__name__, str(exc))

    @ovld
    def make_error(self, ctx, typ: str, message: str):
        print(f"[{ctx}]:", typ, message, file=sys.stderr)
        return ErrorData(type=typ, message=message)

    def fetch_link(self, src: DownloadResult):
        try:
            config.fetch.download(
                url=src.url.url,
                filename=self.pdf_path,
            )
            src.downloaded = True
        except Exception as exc:
            src.error = self.make_error(src.ref, exc)
            return False

        return True

    def fetch(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.initialize_meta()
        for url in locate_all(self.ref):
            src = DownloadResult(
                url=url,
                ref=self.ref,
                downloaded=False,
                error=None,
            )
            self.meta.sources.append(src)
            if self.fetch_link(src):
                self.meta.success = True
                self.write_meta()
                return True
        self.write_meta()
        return False

    def write_meta(self):
        self.meta_path.write_text(yaml.safe_dump(serialize(Metadata, self.meta)))

    def get(self):
        cp = self.cache_policy
        if cp.use and self.meta.success:
            assert self.pdf_path.exists()
            return True
        elif cp.download:
            return self.fetch()
        else:
            return False

    @property
    def fulltext(self) -> Path:
        success = self.get()
        return self.pdf_path if success else None


def fulltext(
    paper: PaperInfo, cache_policy=CachePolicies.USE
) -> Generator[Path, None, None]:
    for link in paper.paper.links:
        pdf = PDF(
            identifier=paper.key,
            title=paper.paper.title,
            ref=f"{link.type}:{link.link}",
            cache_policy=cache_policy,
        )
        if fulltext := pdf.fulltext:
            yield fulltext
