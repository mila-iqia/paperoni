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
from paperoni.sources.scrapers.semantic_scholar import SemanticScholarQueryManager
here = Path(__file__).parent

ss = SemanticScholarQueryManager()
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

async def prepare(
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
                yield author, p

@bear
async def app(page):
    q = Queue()
    debounced = ClientWrap(q, debounce=0.3)
    page["head"].print(
        H.link(rel="stylesheet", href=here.parent / "paperoni" / "default.css")
    )

    author_name = "Amin Emad"

    def confirm_id(auth, int):
        link = auth.links[0].link

        #deleteid = "#area" + link
        #print(deleteid)
        #page[deleteid].delete()

    def get_authors(name):
        authors = []
        stmt = select(sch.Author).filter(sch.Author.name.like(f"%{name}%"))
        try:
            results = list(db.session.execute(stmt))
            for (r,) in results:
                authors.append(r)
                print("links : ")
                for i in r.links:
                    print("Type :", i.type, " Link :", i.link)
        except Exception as e:
            print("Error : ", e)
        return authors

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            print(get_authors(author_name))
            reaserchers = get_authors(author_name)
            tabIDS = []

            results = prepare(researchers=reaserchers,idtype="semantic_scholar",query_name=ss.author_with_papers)
            print("called prepare")
            async for auth, result in results:
                link = auth.links[0].link
                if link not in tabIDS:
                    tabIDS.append(link)
                    author_name_area = H.div["authornamearea"](
                        auth.name,
                        H.br,
                        H.br,
                        auth.links[0].type,
                        H.br,
                        H.a["link"](link, href="https://www.semanticscholar.org/author/" + auth.name+"/"+str(link), target="_blank"),
                        H.div["authoridbuttonarea"](
                            H.button["button"](
                                "Include ID",
                                onclick=(
                                    lambda event, auth=auth: confirm_id(
                                        auth, 1
                                    )
                                ),
                            ),
                            H.button["button", "invalidate"](
                                "Exclude ID",
                                onclick=(
                                    lambda event, auth=auth: confirm_id(
                                        auth, 0
                                    )
                                ),
                            ),
                        )
                    )
                    papers_area = H.div["papersarea"](id="a" + link)
                    area = H.div["authorarea"](
                        author_name_area,
                        papers_area,
                    )(id="area"+link)
                    page.print(area)
                div = html(result)
                valDiv = H.div["validationDiv"](
                        div)
                aid = "#a" + link
                page[aid].print(valDiv)
                
