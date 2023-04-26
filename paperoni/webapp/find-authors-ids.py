"""Simple validation app.
Run with `uvicorn apps.validation:app`
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starbear import ClientWrap, Queue, bear

from paperoni.config import load_config
from paperoni.db import schema as sch
from paperoni.display import html

from collections import Counter
from giving import give
from paperoni.model import Link, UniqueAuthor

here = Path(__file__).parent


async def regenerator(queue, regen, reset):
    gen = regen()
    done = False
    while True:
        if done:
            inp = await queue.get()
        else:
            try:
                inp = await asyncio.wait_for(queue.get(), 0.01)
            except (asyncio.QueueEmpty, asyncio.exceptions.TimeoutError):
                inp = None

        if inp is not None:
            new_gen = regen(inp)
            if new_gen is not None:
                done = False
                gen = new_gen
                reset()
                continue

        try:
            element = next(gen)
        except StopIteration:
            done = True
            continue

        yield element

def _fill_rids(rids, researchers, idtype):
    for researcher in researchers:
        for link in researcher.links:
            if link.type == idtype:
                rids[link.link] = researcher.name

def _getname(x):
    return x.name

def filter_researchers(
    researchers, names=None, before=None, after=None, getname=_getname
):
    if names is not None:
        names = [n.lower() for n in names]
        researchers = [r for r in researchers if getname(r).lower() in names]

    researchers.sort(key=getname)

    if before is not None:
        researchers = [
            r
            for r in researchers
            if getname(r)[: len(before)].lower() < before.lower()
        ]

    if after is not None:
        researchers = [
            r
            for r in researchers
            if getname(r)[: len(after)].lower() > after.lower()
        ]

    return researchers

def prepare(
    researchers,
    idtype,
    query_name,
    minimum=None,
):
    rids = {}
    _fill_rids(rids, researchers, idtype)

    def _ids(x, typ):
        return [link.link for link in x.links if link.type == typ]

    for auq in researchers:
        aname = auq.name
        ids = set(_ids(auq, idtype))
        noids = set(_ids(auq, f"!{idtype}"))

        def find_common(papers):
            common = Counter()
            for p in papers:
                for a in p.authors:
                    for l in a.author.links:
                        if l.type == idtype and l.link in rids:
                            common[rids[l.link]] += 1
            return sum(common.values()), common

        data = [
            (author, *find_common(papers), papers)
            for author, papers in query_name(aname)
            if not minimum or len(papers) > minimum
        ]
        data.sort(key=lambda ap: (-ap[1], -len(ap[-1])))

        for author, _, common, papers in data:
            if not papers:  # pragma: no cover
                continue

            done = False

            (new_id,) = _ids(author, idtype)
            if new_id in ids or new_id in noids:
                give(author=aname, skip_id=new_id)
                continue

            aliases = {*author.aliases, author.name} - {aname}

            def _make(negate=False):
                auth = UniqueAuthor(
                    author_id=auq.author_id,
                    name=aname,
                    affiliations=[],
                    roles=[],
                    aliases=[] if negate else aliases,
                    links=[Link(type=f"!{idtype}", link=new_id)]
                    if negate
                    else author.links,
                )
                if not negate:
                    _fill_rids(rids, [auth], idtype)
                return auth

            papers = [
                (p.releases[0].venue.date.year, i, p)
                for i, p in enumerate(papers)
            ]
            papers.sort(reverse=True)

            give(
                author=author,
                author_name=aname,
                id=new_id,
                npapers=len(papers),
                common=dict(sorted(common.items(), key=lambda x: -x[1])),
                aliases=aliases,
                start_year=papers[-1][0],
                end_year=papers[0][0],
            )

            for _, _, p in papers:
                pass

def prepare_interface(
    researchers,
    idtype,
    query_name,
    minimum=None,
):
    # ID to give to the researcher
    # [option: --id]
    #given_id: Option = None
    given_id = None

    researchers = filter_researchers(researchers)

    if given_id:
        assert len(researchers) == 1
        for auq in researchers:
            yield UniqueAuthor(
                author_id=auq.author_id,
                name=auq.name,
                affiliations=[],
                roles=[],
                aliases=[],
                links=[Link(type=idtype, link=given_id)],
            )

    else:
        yield from prepare(
            researchers=researchers,
            idtype=idtype,
            minimum=minimum,
            query_name=query_name,
        )


@bear
async def app(page):
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3)
    page["head"].print(
        H.link(rel="stylesheet", href=here.parent / "paperoni" / "default.css")
    )
    area = H.div["area"]().autoid()
    page.print(H.span("Validation"))
    page.print(area)

    author_name = "Amin Emad"

    def regen(event=None):
        if event is not None:
            title = event["title"]
            author = event["author"]
            date_start = event["date-start"]
            date_end = event["date-end"]
            return generate(title, author, date_start, date_end)
        return generate()

    def generate(title=None, author=None, date_start=None, date_end=None):
        stmt = select(sch.Paper)
        stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author_name}%"))
            )
        if not all(
            val is "" or val is None
            for val in [title, author, date_start, date_end]
        ):
            stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author_name}%"))
            )
        try:
            results = list(db.session.execute(stmt))
            for (r,) in results:
                yield r
        except Exception as e:
            print("Error : ", e)

    def search(title, author, date_start, date_end):
        stmt = select(sch.Paper)
        # Selecting from the title
        if title is not None and title != "":
            stmt = select(sch.Paper).filter(sch.Paper.title.like(f"%{title}%"))
        # Selecting from author
        if author is not None and author != "":
            stmt = (
                stmt.join(sch.Paper.paper_author)
                .join(sch.PaperAuthor.author)
                .filter(sch.Author.name.like(f"%{author}%"))
            )

        # Selecting from date
        # Joining the tables if any of the dates are set
        if (date_start is not None and date_start != "") or (
            date_end is not None and date_end != ""
        ):
            stmt = stmt.join(sch.Paper.release).join(sch.Release.venue)

        # Filtering for the dates
        if date_start is not None and date_start != "":
            date_start_stamp = int(
                datetime(*map(int, date_start.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date >= date_start_stamp)
        if date_end is not None and date_end != "":
            date_end_stamp = int(
                datetime(*map(int, date_end.split("-"))).timestamp()
            )
            stmt = stmt.filter(sch.Venue.date <= date_end_stamp)

        return stmt

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            regen = regenerator(
                queue=q,
                regen=regen,
                reset=page[area].clear,
            )
            async for result in regen:
                div = html(result)
                valDiv = H.div["validationDiv"](
                        div)
                page[area].print(valDiv)
