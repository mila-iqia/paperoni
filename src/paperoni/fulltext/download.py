import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from typing import Optional

import yaml
from apischema import deserialize, serialize
from ovld import ovld

from ..config import papconf
from ..utils import download
from .locate import URL, find_download_links, ua
from .pdfanal import to_plain


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
    NO_DOWNLOAD = CachePolicy(
        use=True, download=False, refresh_on_new_links=False
    )
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
    def __init__(self, identifier, title, refs, cache_policy=CachePolicies.USE):
        self.identifier = identifier
        self.title = title
        self.refs = refs
        self.cache_policy = cache_policy

        # Set paths
        self.directory = papconf.paths.fulltext / identifier
        self.meta_path = self.directory / "meta.yaml"
        self.pdf_path = self.directory / "fulltext.pdf"
        self.xml_path = self.directory / "fulltext.xml"
        self.text_path = self.directory / "fulltext.txt"
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

    def fetch_link(self, src):
        link = src.ref
        pdf = self.pdf_path
        try:
            download(
                url=src.url.url,
                filename=self.pdf_path,
                headers={"User-Agent": ua.random, **src.url.headers},
            )
            src.downloaded = True
        except Exception as exc:
            src.error = self.make_error(link, exc)
            return False

        dataproc = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf), str(self.xml_path)],
            capture_output=True,
        )
        if dataproc.returncode != 0:
            src.error = self.make_error(
                link, "PdfToTextError", "pdftotext failed to process pdf file"
            )
            return False

        if not self.xml_path.stat().st_size:
            self.pdf_path.unlink()
            self.xml_path.unlink()
            src.error = self.make_error(link, "EmptyError", "the data is empty")
            return False

        dataproc = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf), str(self.xml_path)],
            capture_output=True,
        )
        if dataproc.returncode != 0:
            src.error = self.make_error(
                link, "PdfToTextError", "pdftotext failed to process pdf file"
            )
            return False

        self.text_path.write_text(to_plain(self.xml_path.read_text()))

        return True

    def fetch(self):
        os.makedirs(self.directory, exist_ok=True)
        self.initialize_meta()
        for ref in self.refs:
            for url in find_download_links(ref):
                src = DownloadResult(
                    url=url,
                    ref=ref,
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
        self.meta_path.write_text(yaml.safe_dump(serialize(self.meta)))

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
    def fulltext(self):
        success = self.get()
        return self.text_path.read_text() if success else None
