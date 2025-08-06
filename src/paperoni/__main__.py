import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from gifnoc import add_overlay, cli
from serieux import Auto, Registered, TaggedUnion, serialize, singleton
from serieux.features.tagset import FromEntryPoint

from .config import config
from .display import display, terminal_width
from .fulltext.locate import locate_all
from .fulltext.pdf import CachePolicies, get_pdf
from .model import PaperInfo
from .model.merge import merge_all
from .refinement import fetch_all
from .utils import url_to_id


class Formatter(Registered):
    pass


@singleton("json")
class JSONFormatter(Formatter):
    def __call__(self, papers):
        ser = serialize(list[PaperInfo], list(papers))
        print(json.dumps(ser, indent=4))


@singleton("yaml")
class YAMLFormatter(Formatter):
    def __call__(self, papers):
        ser = serialize(list[PaperInfo], list(papers))
        print(yaml.safe_dump(ser, sort_keys=False))


@singleton("terminal")
class TerminalFormatter(Formatter):
    def __call__(self, papers):
        for i, paper in enumerate(papers):
            if i == 0:
                print("=" * terminal_width)
            display(paper)
            print("=" * terminal_width)


@dataclass
class Discover:
    """Discover papers from various sources."""

    command: Annotated[
        Any, FromEntryPoint("paperoni.discovery", wrap=lambda cls: Auto[cls.query])
    ]

    # Output format
    format: Formatter = TerminalFormatter

    # Top n entries
    top: int = 0

    def run(self):
        papers = self.command()
        if self.top:
            papers = config.focuses.top(n=self.top, pinfos=papers)
        self.format(papers)


def locate(
    # Reference to locate
    # [positional]
    ref: str,
):
    for url in locate_all(ref):
        print(f"\033[36m[{url.info}]\033[0m {url.url}")


def download(
    # Reference to locate
    # [positional]
    # [nargs: +]
    ref: list[str],
    # Cache policy
    # [alias: -p]
    cache_policy: Literal["use", "use_best", "no_download", "force"] = "use",
):
    p = get_pdf(ref, cache_policy=getattr(CachePolicies, cache_policy.upper()))
    print("Downloaded into:", p.pdf_path.resolve())


@dataclass
class Fulltext:
    """Download and process fulltext."""

    run: TaggedUnion[Auto[locate], Auto[download]]


@dataclass
class Refine:
    """Refine paper information."""

    # Link to refine (type:link)
    # [action: append]
    link: list[str]

    # Whether to merge the results
    merge: bool = False

    # Output format
    format: Formatter = TerminalFormatter

    def run(self):
        results = []
        for link in self.link:
            if link.startswith("http"):
                type, link = url_to_id(link)
            else:
                type, link = link.split(":", 1)
            results.extend(fetch_all(type, link))
        if self.merge:
            results = [merge_all(results)]
        self.format(results)


@dataclass
class PaperoniInterface:
    """Paper database"""

    command: TaggedUnion[Discover, Refine, Fulltext]

    def run(self):
        self.command.run()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=None)
    args, remaining = parser.parse_known_args()
    if args.config:
        add_overlay(Path(args.config))
    command = cli(field="paperoni.cli", type=PaperoniInterface, argv=remaining)
    command.run()


if __name__ == "__main__":
    main()
