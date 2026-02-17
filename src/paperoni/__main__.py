import argparse
import asyncio
import itertools
import json
import logging
import random
import shlex
import sys
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator, Literal

import gifnoc
import uvicorn
import yaml
from filelock import FileLock
from gifnoc import add_overlay, cli
from outsight import outsight, send
from outsight.ops import merge, ticktock
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
from serieux.features.filebacked import FileProxy
from serieux.features.partial import Override
from serieux.features.registered import Referenced
from serieux.features.tagset import FromEntryPoint

from .client.utils import login
from .collection.abc import PaperCollection
from .collection.filecoll import FileCollection
from .collection.finder import find_equivalent, paper_index
from .collection.remotecoll import RemoteCollection
from .config import config
from .dash import History
from .discovery.paperoni_v2 import PaperoniV2
from .display import display, print_field, terminal_width
from .fulltext.locate import URL, locate_all
from .fulltext.pdf import PDF, CachePolicies, get_pdf
from .heuristics import simplify_paper
from .model import Link, Paper
from .model.focus import Focuses, Scored, Top
from .model.merge import PaperWorkingSet, merge_all
from .model.utils import paper_has_updated
from .refinement import fetch_all
from .refinement.llm_normalize import normalize_paper
from .richlog import ErrorOccurred, LogEvent, Logger, ProgressiveCount, Statistic
from .utils import deprox, expand_links_dict, prog, soft_fail, url_to_id


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
    def __call__(self, things, typ=None):
        for i, thing in enumerate(things):
            term_display(thing, i)


def norm_args(norm):
    return {which: (which in norm) for which in ("author", "venue", "institution")}


@dataclass
class Productor:
    command: Annotated[
        Any, FromEntryPoint("paperoni.discovery", wrap=lambda cls: Auto[cls.query])
    ]

    async def iterate(self, **kwargs) -> AsyncGenerator[Paper, None]:
        async for p in self.command(**kwargs):
            send(discover=p)
            yield p


@dataclass
class Discover(Productor):
    """Discover papers from various sources."""

    # Output format
    format: Formatter = TerminalFormatter

    # Top n entries
    top: int = 0

    async def run(self):
        typ = Paper
        papers = [p async for p in self.iterate()]
        if self.top:
            papers = config.focuses.top(n=self.top, papers=papers)
            typ = Scored[Paper]
        self.format(papers, typ=typ)


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

        async def run(self):
            if self.ref.startswith("http"):
                ref = ":".join(url_to_id(self.ref) or ["", ""])
            else:
                ref = self.ref

            urls = [url async for url in locate_all(ref)]
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

        async def run(self):
            p = await get_pdf(
                self.ref, cache_policy=getattr(CachePolicies, self.cache_policy.upper())
            )
            self.format(p)
            return p

    # Command to execute
    command: TaggedUnion[Locate, Download]

    async def run(self):
        __trace__ = f"command:{type(self.command).__name__}"  # noqa: F841
        await self.command.run()


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

    # Fields to normalize
    # [action: append]
    norm: set[str] = None

    # Whether to merge the results
    merge: bool = False

    # Whether to force re-running the refine
    force: bool = False

    # Output format
    format: Formatter = TerminalFormatter

    async def run(self):
        results = []
        links = []
        for link in self.link:
            if link.startswith("http"):
                links.append(url_to_id(link))
            else:
                links.append(link.split(":", 1))

        results = [p async for p in fetch_all(links, tags=self.tags, force=self.force)]

        if self.norm:
            results = [
                normalize_paper(paper, force=self.force, **norm_args(self.norm))
                for paper in results
            ]

        if self.merge:
            results = [merge_all(results)]

        self.format(results)


@dataclass
class Work:
    """Discover and work on prospective papers."""

    @dataclass
    class Configure:
        """Configure the workset."""

        n: int
        drop_zero: bool = True
        clear: bool = False

        async def run(self, work: "Work"):
            work_file = work.work_file or config.work_file
            if work_file.exists():
                top = deserialize(
                    Top[Scored[CommentRec[PaperWorkingSet, float]]], work_file
                )
                top.drop_zero = self.drop_zero
                if self.clear:
                    top.entries = []
                elif top.n > self.n:
                    top.entries = list(top)[: self.n]
                    top.resort()
                top.n = self.n
            else:
                top = Top(self.n, drop_zero=self.drop_zero)
            work.save(top)
            print(f"Configured {work_file.resolve()} for n={self.n}")

    @dataclass
    class Get(Productor):
        """Get articles from various sources."""

        # [alias: -U]
        check_paper_updates: bool = False

        async def run(self, work: "Work"):
            ex = work.collection and (await work.collection.exclusions())
            index = paper_index()
            index.index_all(list(work.top))

            async for paper in self.iterate(focuses=work.focuses):
                if ex and paper.key in ex:
                    continue

                if found := find_equivalent(paper, index):
                    found.value.add(paper)
                    new_score = work.focuses.score(found.value.current)
                    if new_score != found.score:
                        # Might be unnecessarily expensive but we'll see
                        work.top.resort()
                    continue

                col_paper = None
                if (
                    work.collection
                    and (col_paper := await work.collection.find_paper(paper))
                    and (
                        not self.check_paper_updates
                        or not paper_has_updated(col_paper, paper)
                    )
                ):
                    continue

                if col_paper:
                    working_set = PaperWorkingSet.make(
                        replace(
                            col_paper,
                            key=paper.key,
                            info=paper.info,
                            score=work.focuses.score(col_paper),
                        )
                    )
                    working_set.add(paper)
                    scored = Scored(work.focuses.score(working_set.current), working_set)

                else:
                    scored = Scored(
                        work.focuses.score(paper), PaperWorkingSet.make(paper)
                    )

                if work.top.add(scored):
                    send(workset_added=1)
                index.index(scored)
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

        async def run(self, work: "Work"):
            worksets = itertools.islice(work.top, self.n) if self.n else work.top
            match self.what:
                case "title":
                    self.format(ws.value.current.title for ws in worksets)
                case "paper":
                    self.format(worksets)
                case "has_pdf":
                    n = total = 0

                    async def gen():
                        nonlocal n, total
                        for ws in worksets:
                            paper = ws.value.current
                            pdf = None
                            total += 1
                            try:
                                pdf = await get_pdf(
                                    [f"{lnk.type}:{lnk.link}" for lnk in paper.links]
                                )
                                n += 1
                            except Exception as exc:
                                print(exc)
                            yield {"has_pdf": pdf is not None, "title": paper.title}

                    self.format(gen(), dict[str, JSON])
                    print(f"{n}/{total} papers have PDFs")

            return worksets

    @dataclass
    class Refine:
        """Refine articles in the workset."""

        # Number of papers to refine, starting from top
        n: int = None

        # Refine tags
        # [action: append]
        # [alias: -t]
        tags: set[str] = field(default_factory=set)

        # Number of refinement loops to perform for each paper
        loops: int = 1

        # Whether to force re-running the refine
        force: bool = False

        async def run(self, work: "Work"):
            statuses = {}
            it = list(itertools.islice(work.top, self.n)) if self.n else work.top

            for i in range(self.loops):

                async def fetch_and_add(sws, i):
                    statuses.update(
                        {
                            (name, key): "done"
                            for paper in sws.value.collected
                            for name, key in paper.info.get("refined_by", {}).items()
                        }
                    )
                    # Loop a bit because refiners can add new links to refine further
                    links = [(lnk.type, lnk.link) for lnk in sws.value.current.links]
                    links.append(("title", sws.value.current.title))
                    if i == 0:
                        send(to_refine=links)
                    async for paper in fetch_all(
                        links,
                        group=";".join([f"{type}:{link}" for type, link in links]),
                        tags=self.tags,
                        force=self.force,
                        statuses=statuses,
                    ):
                        send(refinement=paper)
                        sws.value.add(paper)
                    sws.score = work.focuses.score(sws.value)
                    return sws

                coros = [
                    fetch_and_add(sws, i)
                    for sws in prog(it, name=f"refine{i + 1 if i else ''}")
                ]
                await asyncio.gather(*coros)

            work.top.resort()
            work.save()

    @dataclass
    class Normalize:
        """Normalize the articles in the workset."""

        # Number of papers to normalize, starting from top
        n: int = None

        # Fields not to normalize
        # [action: append]
        # [alias: -x]
        exclude: set[str] = field(default_factory=set)

        # Whether to force re-running the normalization
        force: bool = False

        async def run(self, work: "Work"):
            kwargs = {k: not v for k, v in norm_args(self.exclude).items()}
            it = itertools.islice(work.top, self.n) if self.n else work.top

            for sws in prog(list(it), name="normalize"):
                with soft_fail():
                    p = normalize_paper(sws.value.current, **kwargs, force=self.force)
                    sws.value.current = simplify_paper(p)
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

        # Operations to run on each included paper
        operations: list[Referenced[object]] = field(default_factory=list)

        def _apply_operations(self, p: Paper):
            for o in self.operations:
                p = o(p).new
            return p

        async def run(self, work: "Work"):
            selected = self.extract(
                work,
                stop=self.n,
                filter=lambda sws: sws.score >= self.score,
            )
            if self.operations:
                selected = [self._apply_operations(p) for p in selected]

            try:
                added = await work.collection.add_papers(selected)
            finally:
                # As some papers could be added to the collection before an
                # error is raised, causing a new paper to exists in the
                # collection (with an id) as well as in the work file (with no
                # id), we prefer to rmove more papers than necessary in the work
                # file than duplicating some of the newly added papers. Future
                # get / refine should be able to readd the paper to the work
                # file
                work.save()

            send(collection_include=added)
            return added

    @dataclass
    class Exclude(Extractor):
        """Exclude bottom articles from collection."""

        # Maximum number of papers to exclude
        n: int = None

        # Maximum score for excluding
        score: float = 0.0

        async def run(self, work: "Work"):
            selected = self.extract(
                work,
                stop=None if self.n is None else -self.n,
                filter=lambda sws: sws.score <= self.score,
            )

            try:
                await work.collection.exclude_papers(selected)
            finally:
                work.save()
            send(collection_exclude=len(selected))

    @dataclass
    class Clear(Extractor):
        """Clear the workset."""

        async def run(self, work: "Work"):
            self.extract(work, filter=lambda _: True)
            work.save()

    # Command
    command: TaggedUnion[Configure, View, Get, Refine, Normalize, Include, Exclude, Clear]

    # File containing the working set
    # [alias: -w]
    work_file: Path = None

    # List of focuses
    # [alias: -f]
    focus_file: Path = None

    # Collection file
    # [alias: -c]
    collection_file: Path = None

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
        if not work_file.exists():
            sys.exit(
                f"ERROR: {work_file.resolve()} does not exist. Try running\n    paperoni work configure -n N"
            )
        return deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], work_file)

    def save(self, top=None):
        wfile = deprox(self.work_file or config.work_file)
        wfile.parent.mkdir(exist_ok=True, parents=True)
        dump(
            Top[Scored[CommentRec[PaperWorkingSet, float]]],
            self.top if top is None else top,
            dest=wfile,
        )

    async def run(self):
        __trace__ = f"command:{type(self.command).__name__}"  # noqa: F841
        wf = self.work_file or config.work_file
        lf = wf.with_suffix(".lock")
        with FileLock(lf):
            return await self.command.run(self)


@dataclass
class Coll:
    """Operations on the paper collection."""

    @dataclass
    class Search:
        """Search the paper collection."""

        # Paper ID
        paper_id: int = None

        # Title of the paper
        title: str = None

        # Author of the paper
        # [alias: -a]
        author: str = None

        # Institution of an author
        # [alias: -i]
        institution: str = None

        # Venue name (long or short)
        # [alias: -v]
        venue: str = None

        # Start date (YYYY-MM-DD)
        # [alias --start]
        start_date: date = None

        # End date (YYYY-MM-DD)
        # [alias --end]
        end_date: date = None

        # Flag search
        # [alias: -f]
        flags: set[str] = None

        # Whether to expand links
        expand_links: bool = False

        # Output format
        format: Formatter = TerminalFormatter

        async def run(self, coll: "Coll") -> list[Paper]:
            flags = set() if self.flags is None else self.flags
            papers = [
                replace(
                    p,
                    links=[
                        Link(type=l["type"], link=l["url"])
                        for l in expand_links_dict(p.links)
                        if "url" in l
                    ],
                )
                if self.expand_links
                else p
                async for p in coll.collection.search(
                    paper_id=self.paper_id,
                    title=self.title,
                    author=self.author,
                    institution=self.institution,
                    venue=self.venue,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    include_flags={f for f in flags if not f.startswith("~")},
                    exclude_flags={f[1:] for f in flags if f.startswith("~")},
                )
            ]
            self.format(papers)
            return papers

    @dataclass
    class Import:
        """Import papers from a file."""

        # File to import from
        # [positional]
        file: Path

        async def run(self, coll: "Coll"):
            await coll.collection.add_papers(deserialize(list[Paper], self.file))

    @dataclass
    class Export:
        """Export papers to a file."""

        # File to export to
        # [positional]
        file: Path = None

        async def run(self, coll: "Coll"):
            papers = [p async for p in coll.collection.search()]
            if self.file:
                dump(list[Paper], papers, dest=self.file)
            else:
                print(json.dumps(serialize(list[Paper], papers), indent=4))

    @dataclass
    class Drop:
        """Drop the paper collection."""

        # Whether to force dropping the collection
        force: bool = False

        async def run(self, coll: "Coll"):
            if not self.force:
                # Ask the user for confirmation
                answer = input("Are you sure you want to drop the collection? (Y/n): ")
                if len(answer) > 1:
                    answer = answer.lower()

                self.force = answer in ["Y", "yes"]

            if self.force:
                await coll.collection.drop()
            elif (await coll.collection.count()) or len(
                await coll.collection.exclusions()
            ):
                logging.warning("Collection is not empty. Use --force to drop it.")

    @dataclass
    class Validate:
        """Validate the papers in the collection using the paperoni v2 database."""

        # The paperoni v2 database
        # [optional]
        # [metavar v2]
        paperoni_v2: Auto[PaperoniV2.query] = None

        # Validate papers having a score greater than the threshold
        # [metavar FLOAT]
        threshold: float = None

        async def iterate(
            self, coll: "Coll" = None, **kwargs
        ) -> AsyncGenerator[Paper, None]:
            if self.paperoni_v2 is not None:
                validated = 0
                total = 0
                async for paper_v2 in self.paperoni_v2(**kwargs):
                    paper_v2: Paper
                    total += 1

                    if "valid" not in paper_v2.flags:
                        continue

                    validated += 1

                    yield paper_v2

                    send(progress=("Validated v2 papers", validated, total))

                send(progress=("Validated v2 papers", None, total))

            else:
                score_threshold = self.threshold or config.autovalidate.score_threshold

                async for paper in coll.collection.search():
                    paper: Paper

                    if (
                        "valid" in paper.flags
                        or (paper.score or config.focuses.score(paper)) < score_threshold
                    ):
                        continue

                    yield paper

        async def run(self, coll: "Coll"):
            ignored = 0
            validated = 0
            count = 0

            async for paper in self.iterate(coll=coll):
                count += 1

                if coll_paper := await coll.collection.find_paper(paper):
                    if "invalid" in coll_paper.flags:
                        ignored += 1
                        continue

                    validated += 1
                    coll_paper.flags.add("valid")
                    await coll.collection.edit_paper(coll_paper)

                if ignored and ignored != count:
                    send(progress=("Ignored papers", ignored, count))

                send(progress=("Validated papers", validated, count))

    @dataclass
    class Diff:
        """Diff the paper collection and another collection.

        The output directory will contain two files:
        - missing.json: Papers in the other collection that are not in the current collection
        - extra.json: Papers in the current collection that are not in the other collection
        """

        # The other collection
        # [positional]
        other_collection_path: str

        # Output directory
        out: Path

        # Format of the output files
        # [alias: --fmt]
        format: Literal["json", "yaml"] = "json"

        async def run(self, coll: "Coll"):
            other_collection = FileCollection(file=Path(self.other_collection_path))
            missings = []
            extras = []

            async for paper in other_collection.search():
                if not await coll.collection.find_paper(paper):
                    missings.append(paper)

            self.out.mkdir(exist_ok=True, parents=True)
            (self.out / f"missing.{self.format}").unlink(missing_ok=True)
            await FileCollection(file=self.out / f"missing.{self.format}").add_papers(
                missings
            )

            async for paper in coll.collection.search():
                if not await other_collection.find_paper(paper):
                    extras.append(paper)

            (self.out / f"extra.{self.format}").unlink(missing_ok=True)
            await FileCollection(file=self.out / f"extra.{self.format}").add_papers(
                extras
            )

    @dataclass
    class Operate:
        """Operate over the paper collection."""

        # Operation to perform
        # [positional]
        operation: Referenced[object]

        async def run(self, coll: "Coll"):
            results = await coll.collection.operate(self.operation)
            print(f"Modified {len(results)} papers")
            return results

    # Command to execute
    command: TaggedUnion[Search, Import, Export, Drop, Validate, Diff, Operate]

    # Collection string. Can be a remote collection URL or a path.
    # [alias: -c]
    collection_path: str = None

    @cached_property
    def collection(self) -> PaperCollection:
        if self.collection_path:
            if self.collection_path.startswith("http"):
                return RemoteCollection(endpoint=self.collection_path)
            else:
                return FileCollection(file=Path(self.collection_path))
        else:
            return config.collection

    async def run(self):
        await self.command.run(self)


@dataclass
class Batch:
    """Run a batch of commands from a YAML or JSON file."""

    # Path to the batch file
    # [positional]
    batch_file: Path

    async def run(self):
        batch = deserialize(dict[str, PaperoniCommand], self.batch_file)
        for name, cmd in batch.items():
            __trace__ = f"step:{name}"  # noqa: F841
            batch_descr = f"Batch: start step {name}"
            with soft_fail(batch_descr):
                send(event=batch_descr)
                await cmd.run()


@dataclass
class Focus:
    """Operations on the focuses."""

    @dataclass
    class AutoFocus:
        """Automatically add focuses."""

        # Timespan to consider for autofocus
        # [alias: -t]
        timespan: timedelta = timedelta(weeks=52)

        async def run(self, focus: "Focus"):
            focuses = focus.focuses or config.focuses
            start_date = datetime.now() - self.timespan
            start_date = start_date.date().replace(month=1, day=1)
            focuses.update(
                [p async for p in focus.collection.search(start_date=start_date)],
                config.autofocus,
            )
            focuses.save()
            return focuses

    # Command to execute
    command: TaggedUnion[AutoFocus]

    # List of focuses
    # [option: -f]
    focuses: Focuses @ FileProxy() = None

    # Collection file
    # [alias: -c]
    collection_file: Path = None

    @cached_property
    def collection(self):
        if self.collection_file:
            return FileCollection(file=self.collection_file)
        else:
            return config.collection

    async def run(self):
        await self.command.run(self)


@dataclass
class Serve:
    """Serve paperoni through a Rest API."""

    # Host to bind to
    host: str = None

    # Port to bind to
    # [alias: -p]
    port: int = None

    # Enable auto-reload for development
    # [alias: -r]
    reload: bool = False

    # Whether to enable auth
    auth: bool = True

    # Collection file
    # [alias: -c]
    collection_file: Path = None

    async def run(self):
        from .web import create_app

        if self.auth:
            overrides = {}
        else:
            overrides = {
                "paperoni.server.auth.force_user": {"email": "__admin__"},
                "paperoni.server.auth.capabilities.user_overrides": {
                    "__admin__": ["admin"]
                },
            }
        if self.collection_file:
            overrides["paperoni.collection"] = Override(
                {
                    "$class": f"{FileCollection.__module__}:{FileCollection.__qualname__}",
                    "file": str(self.collection_file.resolve()),
                }
            )
        with gifnoc.overlay(overrides):
            app = create_app()
            ssl_config = config.server.ssl
            ssl_kwargs = {}
            if ssl_config and ssl_config.enabled:
                ssl_kwargs["ssl_certfile"] = ssl_config.cert_file
                ssl_kwargs["ssl_keyfile"] = ssl_config.key_file
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=config.server.host if self.host is None else self.host,
                    port=config.server.port if self.port is None else self.port,
                    reload=self.reload,
                    **ssl_kwargs,
                )
            )
            await server.serve()

    def no_dash(self):
        return True


@dataclass
class _PaperoniLogin:
    # Endpoint to login to
    endpoint: str = "http://localhost:8000"

    def login(self):
        return login(self.endpoint)


@dataclass
class Login:
    """Login to a service."""

    @dataclass(frozen=True)
    class LoginFromEntryPoint(FromEntryPoint):
        @cached_property
        def elements(self):
            # hack to avoid FromEntryPoint.default=Auto[_PaperoniLogin.login]
            # failing with:
            # TypeError: sequence item 0: expected str instance, NoneType found

            return {"paperoni": Auto[_PaperoniLogin.login]} | super().elements

    service: Annotated[
        Any,
        LoginFromEntryPoint(
            "paperoni.discovery",
            wrap=lambda cls: Auto[cls.login] if getattr(cls, "login", None) else None,
        ),
    ] = "paperoni"

    async def run(self):
        match token := self.service():
            case str():
                print_field("Access token", token)


PaperoniCommand = TaggedUnion[
    Discover, Refine, Fulltext, Work, Coll, Batch, Focus, Serve, Login
]


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

    # Store a rich JSONL log
    rich_log: bool = False

    def __post_init__(self):
        if self.dash is None and not self.log:
            self.dash = sys.stdout.isatty()

    def get_logfile(self):
        logdir = config.data_path / "logs"
        logdir.mkdir(exist_ok=True, parents=True)
        now = datetime.now()
        rand = random.randint(0, 9999)
        logname = now.strftime("%Y%m%d_%H%M%S") + f"_{rand:04d}.jsonl"
        return logdir / logname

    async def run(self):
        __trace__ = f"command:{type(self.command).__name__}"  # noqa: F841
        logfile = None
        if self.dash and not getattr(self.command, "no_dash", lambda: False)():
            enable_dash()
        if self.log:
            enable_log()
        if self.rich_log:
            logfile = self.get_logfile()
            enable_rich_log(logfile)
        # The program hangs if it ends before outsight can set itself up,
        # so we'll sleep a bit until that's solved.
        time.sleep(0.1)
        send(root_command=self)
        if self.report:
            if not config.reporters:
                sys.exit("No reporters are defined in the config for --report")
            with Report(
                description="`" + " ".join(map(shlex.quote, sys.argv)) + "`",
                reporters=config.reporters,
            ) as report:
                await self.command.run()
                if logfile and config.server:
                    url = f"{config.server.external_host}"
                    report.set_message(f"[View report]({url}/report/{logfile.stem})")
        else:
            await self.command.run()


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


@dataclass
class CommandDescription(LogEvent):
    command: PaperoniInterface


def enable_rich_log(logfile):
    def erryield(fn):
        async def wrapped(*args, **kwargs):
            try:
                async for x in fn(*args, **kwargs):
                    yield x
            except Exception as exc:
                yield ErrorOccurred(
                    context=[f"richlog:{fn.__name__}"],
                    exception=exc,
                )

        return wrapped

    @erryield
    def group(name, stream, key_fn, count_fn=lambda x: 1):
        async def func(stream):
            async for group in stream.buffer(ticktock(1)):
                origins = Counter()
                for entry in group:
                    origin = key_fn(entry) or "unspecified"
                    origins[origin] += count_fn(entry)
                for origin, count in origins.items():
                    event = ProgressiveCount(
                        category=name,
                        origin=origin,
                        count=count,
                    )
                    yield event

        return func(stream)

    @erryield
    async def exceptions(sent):
        async for exc, ctx in sent:
            yield ErrorOccurred(context=ctx, exception=exc)

    @erryield
    def progcount(name, stream):
        async def count(stream):
            async for group in stream.buffer(ticktock(1)):
                yield ProgressiveCount(
                    category=name,
                    origin="all",
                    count=len(group),
                )

        return count(stream)

    @erryield
    def statistic(name, stream):
        async def make(stream):
            async for x in stream:
                yield Statistic(name=name, value=x)

        return make(stream)

    @erryield
    async def root_command(sent):
        async for x in sent["root_command"]:
            yield CommandDescription(command=x)

    @outsight.add
    async def rich_log(sent):
        def _discover_origin(pinfo):
            for src in pinfo.info.get("discovered_by", {}):
                return src
            else:
                return None

        with Logger(logfile) as logger:
            async for event in merge(
                group("Discovered", sent["discover"], _discover_origin),
                group("Prompts", sent["prompt"], lambda p: p),
                group(
                    "Input tokens",
                    sent["prompt", "input_tokens"],
                    lambda p: p[0],
                    lambda p: p[1],
                ),
                group(
                    "Output tokens",
                    sent["prompt", "output_tokens"],
                    lambda p: p[0],
                    lambda p: p[1],
                ),
                progcount("Attempted refinements", sent["to_refine"]),
                progcount("Successful refinements", sent["refinement"]),
                progcount("Added to workset", sent["workset_added"]),
                statistic("Included in collection", sent["collection_include"]),
                statistic("Excluded from collection", sent["collection_exclude"]),
                exceptions(sent["exception", "context"]),
                root_command(sent),
            ):
                try:
                    logger.log(event)
                except Exception as exc:
                    logger.log(
                        ErrorOccurred(
                            context=["richlog:logging"],
                            exception=exc,
                        )
                    )
        print("Log file:", logfile.resolve())


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
            values = [f"{paper.title}" for paper in group]
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
        asyncio.run(command.run())


if __name__ == "__main__":
    main()
