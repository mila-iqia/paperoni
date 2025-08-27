import argparse
import itertools
import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from gifnoc import add_overlay, cli
from outsight import outsight, send
from serieux import (
    Auto,
    CommentRec,
    Registered,
    TaggedUnion,
    deserialize,
    dump,
    serialize,
    singleton,
)
from serieux.features.tagset import FromEntryPoint

from .collection.filecoll import FileCollection
from .config import config
from .dash import History
from .display import display, terminal_width
from .fulltext.locate import locate_all
from .fulltext.pdf import CachePolicies, get_pdf
from .model import PaperInfo
from .model.focus import Focuses, Scored, Top
from .model.merge import PaperWorkingSet, merge_all
from .refinement import fetch_all
from .utils import prog, url_to_id


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
class Productor:
    command: Annotated[
        Any, FromEntryPoint("paperoni.discovery", wrap=lambda cls: Auto[cls.query])
    ]

    def iterate(self, **kwargs):
        for p in self.command(**kwargs):
            send(discover=p)
            yield p


@dataclass
class Discover(Productor):
    """Discover papers from various sources."""

    # Output format
    format: Formatter = TerminalFormatter

    # Top n entries
    top: int = 0

    def run(self):
        papers = self.iterate()
        if self.top:
            papers = config.focuses.top(n=self.top, pinfos=papers)
        self.format(papers)


@dataclass
class Fulltext:
    """Download and process fulltext."""

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

    run: TaggedUnion[Auto[locate], Auto[download]]


@dataclass
class Refine:
    """Refine paper information."""

    # Link to refine (type:link)
    # [action: append]
    link: list[str]

    # Tags to refine
    # [action: append]
    # [alias: -t]
    tags: list[str] = field(default_factory=list)

    # Whether to force re-running the refine
    force: bool = False

    # Whether to merge the results
    merge: bool = False

    # Output format
    format: Formatter = TerminalFormatter

    def __post_init__(self):
        self.tags = set(self.tags)

    def run(self):
        results = []
        for link in self.link:
            if link.startswith("http"):
                type, link = url_to_id(link)
            else:
                type, link = link.split(":", 1)
            results.extend(fetch_all(type, link, tags=self.tags, force=self.force))
        if self.merge:
            results = [merge_all(results)]
        self.format(results)


@dataclass
class Work:
    """Discover and work on prospective papers."""

    @dataclass
    class Get(Productor):
        """Get articles from various sources."""

        def run(self, work):
            ex = work.collection and work.collection.exclusions
            for pinfo in self.iterate(focuses=work.focuses):
                if ex and pinfo.key in ex:
                    continue
                scored = Scored(work.focuses.score(pinfo), PaperWorkingSet.make(pinfo))
                work.top.add(scored)
            work.save()

    @dataclass
    class View:
        """View the articles in the workset."""

        # Output format
        format: Formatter = TerminalFormatter

        # Number of papers to view
        n: int = None

        def run(self, work):
            it = itertools.islice(work.top, self.n) if self.n else work.top
            self.format(Scored(ws.score, ws.value.current) for ws in it)

    @dataclass
    class Refine:
        """Refine articles in the workset."""

        # Number of papers to refine, starting from top
        n: int = None

        def run(self, work):
            statuses = {}
            focuses = deserialize(Focuses, work.focuses or config.focuses)
            it = itertools.islice(work.top, self.n) if self.n else work.top
            jobs = [
                (sws.value, sws, lnk) for sws in it for lnk in sws.value.current.links
            ]
            for ws, sws, lnk in prog(jobs, name="refine"):
                statuses.update(
                    {
                        (name, key): "done"
                        for pinfo in ws.collected
                        for name, key in pinfo.info.get("refined_by", {}).items()
                    }
                )
                for pinfo in fetch_all(lnk.type, lnk.link, statuses=statuses):
                    ws.add(pinfo)
                    sws.score = focuses.score(ws)
            work.top.resort()
            work.save()

    # Command
    command: TaggedUnion[Get, View, Refine]

    # File containing the working set
    # [alias: -w]
    workfile: Path = None

    # List of focuses
    # [alias: -f]
    focus_file: Path = None

    # Collection file
    # [alias: -c]
    collection_dir: Path = None

    # Number of papers to keep in the working set
    n: int = 10

    @cached_property
    def focuses(self):
        if self.focus_file:
            return deserialize(Focuses, self.focus_file)
        else:
            return config.focuses

    @cached_property
    def collection(self):
        if self.collection_dir:
            return FileCollection(self.collection_dir)
        else:
            return config.collection

    @cached_property
    def top(self):
        workfile = self.workfile or config.workfile
        if workfile.exists():
            top = deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], workfile)
        else:
            top = Top(self.n)
        return top

    def save(self):
        dump(
            Top[Scored[CommentRec[PaperWorkingSet, float]]],
            self.top,
            dest=self.workfile or config.workfile,
        )

    def run(self):
        self.command.run(self)


@dataclass
class PaperoniInterface:
    """Paper database"""

    # Command to execute
    command: TaggedUnion[Discover, Refine, Fulltext, Work]

    # Enable rich dashboard
    dash: bool = True

    def run(self):
        if self.dash:
            enable_dash()
        self.command.run()


def enable_dash():
    @outsight.add
    async def show_progress(sent, dash):
        async for name, sofar, total in sent["progress"]:
            dash.add_progress(name, sofar, total)

    @outsight.add
    async def show_paper_stats(sent, dash):
        async for group in sent["discover"].roll(5, partial=True):
            values = [f"{pinfo.paper.title}" for pinfo in group]
            dash["titles"] = History(values)

    @outsight.add
    async def show_requests(sent, dash):
        async for group in sent["url", "params", "response"].roll(5, partial=True):
            values = [
                f"[{resp.status_code}] {req} {params or ''}"
                for req, params, resp in group
            ]
            dash["request"] = History(values)

    @outsight.add
    async def show_score_stats(sent, dash):
        min_score = None
        max_score = None
        count = 0
        async for score in sent["score"]:
            if score == 0:
                continue
            count += 1
            if min_score is None or score < min_score:
                min_score = score
            if max_score is None or score > max_score:
                max_score = score
            dash["score"] = (
                f"{score}   [bold green]max: {max_score}[/bold green]   [bold blue]count: {count}[/bold blue]"
            )

    @outsight.add
    async def show_prompt(sent, dash):
        async for group in sent["prompt", "model", "input"].roll(5, partial=True):
            values = [f"{model} {prompt} {input}" for prompt, model, input in group]
            dash["prompt"] = History(values)


def main():
    with outsight:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config", default=None)
        args, remaining = parser.parse_known_args()
        if args.config:
            add_overlay(Path(args.config))
        command = cli(field="paperoni.cli", type=PaperoniInterface, argv=remaining)
        command.run()


if __name__ == "__main__":
    main()
