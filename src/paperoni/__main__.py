import argparse
import itertools
import json
import shlex
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Generator, Literal

import uvicorn
import yaml
from gifnoc import add_overlay, cli
from outsight import outsight, send
from outsight.ops import ticktock
from ovld import ovld
from rapporteur.report import Report
from serieux import (
    JSON,
    Auto,
    AutoRegistered,
    CommentRec,
    TaggedUnion,
    auto_singleton,
    deserialize,
    dump,
    serialize,
)
from serieux.features.tagset import FromEntryPoint

from paperoni.refinement.llm_normalize import normalize_paper

from .collection.abc import PaperCollection
from .collection.filecoll import FileCollection
from .collection.finder import Finder
from .config import config
from .dash import History
from .display import display, terminal_width
from .fulltext.locate import URL, locate_all
from .fulltext.pdf import PDF, CachePolicies, get_pdf
from .model import PaperInfo
from .model.classes import Paper
from .model.focus import Focuses, Scored, Top
from .model.merge import PaperWorkingSet, merge_all
from .model.utils import paper_has_updated
from .refinement import fetch_all
from .utils import deprox, prog, soft_fail, url_to_id


class Formatter(AutoRegistered):
    def serialize(self, things, typ=None):
        things = list(things)
        if not things:
            return []
        else:
            typ = typ or type(things[0])
            return serialize(list[typ], list(things))


@auto_singleton("json")
class JSONFormatter(Formatter):
    def __call__(self, things, typ=None):
        ser = self.serialize(things, typ=typ)
        print(json.dumps(ser, indent=4))


@auto_singleton("yaml")
class YAMLFormatter(Formatter):
    def __call__(self, things, typ=None):
        ser = self.serialize(things, typ=typ)
        print(yaml.safe_dump(ser, sort_keys=False))


@ovld
def term_display(obj: object, i: int):
    if i == 0:
        print("=" * terminal_width)
    display(obj)
    print("=" * terminal_width)


@ovld
def term_display(x: str, i: int):
    print(x)


@auto_singleton("terminal")
class TerminalFormatter(Formatter):
    def __call__(self, things):
        for i, thing in enumerate(things):
            term_display(thing, i)


@dataclass
class Productor:
    command: Annotated[
        Any, FromEntryPoint("paperoni.discovery", wrap=lambda cls: Auto[cls.query])
    ]

    def iterate(self, **kwargs) -> Generator[PaperInfo, None, None]:
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

    @dataclass
    class Locate:
        # Reference to locate
        # [positional]
        ref: str

        def format(self, urls: list[URL]):
            for url in urls:
                print(f"\033[36m[{url.info}]\033[0m {url.url}")

        def run(self):
            if self.ref.startswith("http"):
                ref = ":".join(url_to_id(self.ref) or ["", ""])
            else:
                ref = self.ref

            urls = list(locate_all(ref))
            self.format(urls)

            return urls

    @dataclass
    class Download:
        # Reference to locate
        # [positional]
        # [nargs: +]
        ref: list[str]
        # Cache policy
        # [alias: -p]
        cache_policy: Literal["use", "use_best", "no_download", "force"] = "use"

        def format(self, pdf: PDF):
            print("Downloaded into:", pdf.pdf_path.resolve())

        def run(self):
            p = get_pdf(
                self.ref, cache_policy=getattr(CachePolicies, self.cache_policy.upper())
            )
            self.format(p)
            return p

    # Command to execute
    command: TaggedUnion[Locate, Download]

    def run(self):
        self.command.run()


@dataclass
class Refine:
    """Refine paper information."""

    # Link to refine (type:link)
    # [action: append]
    link: list[str]

    # Refine tags
    # [action: append]
    # [alias: -t]
    tags: set[str] = field(default_factory=set)

    # Whether to force re-running the refine
    force: bool = False

    # Whether to merge the results
    merge: bool = False

    # Output format
    format: Formatter = TerminalFormatter

    def run(self):
        results = []
        links = []
        for link in self.link:
            if link.startswith("http"):
                links.append(url_to_id(link))
            else:
                links.append(link.split(":", 1))

        results = list(fetch_all(links, tags=self.tags, force=self.force))

        if self.merge:
            results = [merge_all(results)]
        self.format(results)


@dataclass
class Work:
    """Discover and work on prospective papers."""

    @dataclass
    class Get(Productor):
        """Get articles from various sources."""

        def run(self, work: "Work"):
            ex = work.collection and work.collection.exclusions

            find = Finder(
                title_finder=lambda scored: scored.value.current.title,
                links_finder=lambda scored: scored.value.current.links,
                authors_finder=lambda scored: scored.value.current.authors,
                id_finder=lambda scored: getattr(scored.value.current, "id", None),
            )
            find.add(list(work.top))

            for pinfo in self.iterate(focuses=work.focuses):
                if ex and pinfo.key in ex:
                    continue

                if found := find.find(pinfo.paper):
                    found.value.add(pinfo)
                    new_score = work.focuses.score(found.value.current)
                    if new_score != found.score:
                        # Might be unnecessarily expensive but we'll see
                        work.top.resort()
                    continue

                col_paper = None
                if (
                    work.collection
                    and (col_paper := work.collection.find_paper(pinfo.paper))
                    and not paper_has_updated(col_paper, pinfo.paper)
                ):
                    continue

                if col_paper:
                    working_set = PaperWorkingSet.make(
                        PaperInfo(
                            paper=col_paper,
                            key=pinfo.key,
                            info=pinfo.info,
                            score=work.focuses.score(col_paper),
                        )
                    )
                    working_set.add(pinfo)
                    scored = Scored(work.focuses.score(working_set.current), working_set)

                else:
                    scored = Scored(
                        work.focuses.score(pinfo), PaperWorkingSet.make(pinfo)
                    )

                work.top.add(scored)
                find.add([scored])
            work.save()

    @dataclass
    class View:
        """View the articles in the workset."""

        # What to view
        # [positional]
        what: Literal["paper", "has_pdf", "title"] = "paper"

        # Output format
        format: Formatter = TerminalFormatter

        # Number of papers to view
        n: int = None

        def run(self, work: "Work"):
            worksets = itertools.islice(work.top, self.n) if self.n else work.top
            papers: list[Scored[Paper]] = [
                Scored(ws.score, ws.value.current) for ws in worksets
            ]
            match self.what:
                case "title":
                    self.format(p.value.title for p in papers)
                case "paper":
                    self.format(papers)
                case "has_pdf":
                    n = total = 0

                    def gen():
                        nonlocal n, total
                        for p in papers:
                            paper = p.value
                            pdf = None
                            total += 1
                            try:
                                pdf = get_pdf(
                                    [f"{lnk.type}:{lnk.link}" for lnk in paper.links]
                                )
                                n += 1
                            except Exception as exc:
                                print(exc)
                            yield {"has_pdf": pdf is not None, "title": paper.title}

                    self.format(gen(), dict[str, JSON])
                    print(f"{n}/{total} papers have PDFs")

            return papers

    @dataclass
    class Refine:
        """Refine articles in the workset."""

        # Number of papers to refine, starting from top
        n: int = None

        # Refine tags
        # [action: append]
        # [alias: -t]
        tags: set[str] = field(default_factory=set)

        # Whether to force re-running the refine
        force: bool = False

        # Whether to normalize the paper
        norm: bool = False

        # Number of refinement loops to perform for each paper
        loops: int = 1

        def run(self, work: "Work"):
            statuses = {}
            it = itertools.islice(work.top, self.n) if self.n else work.top

            for sws in prog(list(it), name="refine"):
                statuses.update(
                    {
                        (name, key): "done"
                        for pinfo in sws.value.collected
                        for name, key in pinfo.info.get("refined_by", {}).items()
                    }
                )
                for i in range(self.loops):
                    # Loop a bit because refiners can add new links to refine further
                    links = [(lnk.type, lnk.link) for lnk in sws.value.current.links]
                    links.append(("title", sws.value.current.title))
                    if i == 0:
                        send(to_refine=links)
                    for pinfo in fetch_all(
                        links,
                        group=";".join([f"{type}:{link}" for type, link in links]),
                        tags=self.tags,
                        force=self.force,
                        statuses=statuses,
                    ):
                        send(refinement=pinfo)
                        if self.norm:
                            pinfo.paper = normalize_paper(pinfo.paper, force=self.force)
                        sws.value.add(pinfo)
                        sws.score = work.focuses.score(sws.value)

            work.top.resort()
            work.save()

    @dataclass
    class Extractor:
        def extract(self, work: "Work", filter, start=0, stop=None):
            if start or stop:
                it = itertools.islice(work.top, start, stop)
            else:
                it = iter(work.top)
            selected = [sws for sws in it if filter(sws)]
            work.top.discard_all(selected)
            return [s.value.current for s in selected]

    @dataclass
    class Include(Extractor):
        """Include top articles to collection."""

        # Maximum number of papers to include
        n: int = None

        # Minimum score for saving
        score: float = 0.1

        def run(self, work: "Work"):
            selected = self.extract(
                work,
                stop=self.n,
                filter=lambda sws: sws.score >= self.score,
            )

            try:
                added = work.collection.add_papers(selected)
            finally:
                # As some papers could be added to the collection before an
                # error is raised, causing a new paper to exists in the
                # collection (with an id) as well as in the work file (with no
                # id), we prefer to rmove more papers than necessary in the work
                # file than duplicating some of the newly added papers. Future
                # get / refine should be able to readd the paper to the work
                # file
                work.save()

            return added

    @dataclass
    class Exclude(Extractor):
        """Exclude bottom articles from collection."""

        # Maximum number of papers to exclude
        n: int = None

        # Maximum score for excluding
        score: float = 0.0

        def run(self, work: "Work"):
            selected = self.extract(
                work,
                stop=None if self.n is None else -self.n,
                filter=lambda sws: sws.score <= self.score,
            )

            try:
                work.collection.exclude_papers(selected)
            finally:
                work.save()

    @dataclass
    class Clear(Extractor):
        """Clear the workset."""

        def run(self, work: "Work"):
            self.extract(work, filter=lambda _: True)
            work.save()

    # Command
    command: TaggedUnion[Get, View, Refine, Include, Exclude, Clear]

    # File containing the working set
    # [alias: -w]
    work_file: Path = None

    # List of focuses
    # [alias: -f]
    focus_file: Path = None

    # Collection dir
    # [alias: -c]
    collection_file: Path = None

    # Number of papers to keep in the working set
    n: int = 1000

    @cached_property
    def focuses(self):
        if self.focus_file:
            return deserialize(Focuses, self.focus_file)
        else:
            return config.focuses

    @cached_property
    def collection(self):
        if self.collection_file:
            return FileCollection(file=self.collection_file)
        else:
            return config.collection

    @cached_property
    def top(self):
        work_file = self.work_file or config.work_file
        if work_file.exists():
            top = deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], work_file)
        else:
            top = Top(self.n)
        return top

    def save(self):
        wfile = deprox(self.work_file or config.work_file)
        wfile.parent.mkdir(exist_ok=True, parents=True)
        dump(
            Top[Scored[CommentRec[PaperWorkingSet, float]]],
            self.top,
            dest=wfile,
        )

    def run(self):
        self.command.run(self)


@dataclass
class Coll:
    """Operations on the paper collection."""

    @dataclass
    class Search:
        """Search the paper collection."""

        # Title of the paper
        title: str = None

        # Author of the paper
        # [alias: -a]
        author: str = None

        # Institution of an author
        # [alias: -i]
        institution: str = None

        # Output format
        format: Formatter = TerminalFormatter

        def run(self, coll: "Coll") -> list[Paper]:
            papers = list(
                coll.collection.search(
                    title=self.title, author=self.author, institution=self.institution
                )
            )
            self.format(papers)
            return papers

    # Command to execute
    command: TaggedUnion[Search]

    # Collection dir
    # [alias: -c]
    collection_file: Path = None

    @cached_property
    def collection(self) -> PaperCollection:
        if self.collection_file:
            return FileCollection(file=self.collection_file)
        else:
            return config.collection

    def run(self):
        self.command.run(self)


@dataclass
class Batch:
    """Run a batch of commands from a YAML or JSON file."""

    # Path to the batch file
    # [positional]
    batch_file: Path

    def run(self):
        batch = deserialize(dict[str, PaperoniCommand], self.batch_file)
        for name, cmd in batch.items():
            batch_descr = f"Batch: start step {name}"
            with soft_fail(batch_descr):
                send(event=batch_descr)
                cmd.run()


@dataclass
class Focus:
    """Operations on the focuses."""

    @dataclass
    class AutoFocus:
        """Automatically add focuses."""

        # Timespan to consider for autofocus
        # [alias: -t]
        timespan: timedelta = timedelta(weeks=52)

        def run(self, focus: "Focus"):
            start_date = datetime.now() - self.timespan
            start_date = start_date.date().replace(month=1, day=1)
            focus.focuses.update(
                focus.collection.search(start_date=start_date), config.autofocus
            )

            dump(Focuses, focus.focuses, dest=focus._autofocus_file)
            return focus.focuses

    # Command to execute
    command: TaggedUnion[AutoFocus]

    # List of focuses
    # [alias: -f]
    focus_file: Path = field(
        default_factory=lambda: (
            config.metadata.focuses.file and config.metadata.focuses.file.exists()
        )
        and config.metadata.focuses.file
        or None
    )

    # Collection dir
    # [alias: -c]
    collection_file: Path = None

    def __post_init__(self):
        self._autofocus_file = (
            self.focus_file.parent / f"auto{self.focus_file.name}"
            or config.metadata.focuses.autofile
        )

    @cached_property
    def focuses(self):
        return deserialize(Focuses, self.focus_file)

    @cached_property
    def collection(self):
        if self.collection_file:
            return FileCollection(file=self.collection_file)
        else:
            return config.collection

    def run(self):
        self.command.run(self)


@dataclass
class Serve:
    """Serve paperoni through a Rest API."""

    # Host to bind to
    host: str = "127.0.0.1"

    # Port to bind to
    # [alias: -p]
    port: int = 8000

    # Enable auto-reload for development
    # [alias: -r]
    reload: bool = False

    def run(self):
        from paperoni.restapi import create_app

        app = create_app()
        uvicorn.run(app, host=self.host, port=self.port, reload=self.reload)

    def no_dash(self):
        return True


PaperoniCommand = TaggedUnion[Discover, Refine, Fulltext, Work, Coll, Batch, Focus, Serve]


@dataclass
class PaperoniInterface:
    """Paper database"""

    # Command to execute
    command: PaperoniCommand

    # Enable rich dashboard
    dash: bool = None

    # Enable slow log
    log: bool = False

    # Report the execution results
    report: bool = False

    def __post_init__(self):
        if self.dash is None and not self.log:
            self.dash = sys.stdout.isatty()

    def run(self):
        if self.dash and not getattr(self.command, "no_dash", lambda: False)():
            enable_dash()
        if self.log:
            enable_log()
        if self.report:
            if not config.reporters:
                sys.exit("No reporters are defined in the config for --report")
            with Report(
                description="`" + " ".join(map(shlex.quote, sys.argv)) + "`",
                reporters=config.reporters,
            ):
                self.command.run()
        else:
            self.command.run()


def enable_log():
    @outsight.add
    async def slow_log(sent):
        def checkpoint():
            for k, x in counts.items():
                (n, msg) = x
                if n:
                    print(msg.format(n))
                x[0] = 0

        counts = {
            "discover": [0, "Discovered {} papers"],
            "to_refine": [0, "Refinement attempts: {}"],
            "refinement": [0, "Successful refinements: {}"],
        }
        async for group in sent.buffer(ticktock(1)):
            for entry in group:
                if "event" in entry:
                    checkpoint()
                    print(entry["event"])
                elif "prompt" in entry:
                    checkpoint()
                    print("Prompt {model} on {input}".format(**entry))
                else:
                    for k, x in counts.items():
                        if k in entry:
                            x[0] += 1
            checkpoint()


def enable_dash():
    @outsight.add
    async def show_events(sent, dash):
        async for messages in sent["event"].roll(5, partial=True):
            dash["event"] = History(messages)

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
