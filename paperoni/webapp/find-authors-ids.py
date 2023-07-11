"""Simple validation app.
Run with `uvicorn apps.validation:app`
"""

import asyncio
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from giving import give
from hrepr import H
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starbear import ClientWrap, Queue, bear

from paperoni.config import load_config
from paperoni.db import schema as sch
from paperoni.display import html
from paperoni.model import Link, UniqueAuthor
from paperoni.sources.scrapers.semantic_scholar import (
    SemanticScholarQueryManager,
)

here = Path(__file__).parent

ss = SemanticScholarQueryManager()


def _fill_rids(rids, researchers, idtype):
    for researcher in researchers:
        for link in researcher.links:
            strippedtype = (
                link.type[1:] if link.type.startswith("!") else link.type
            )
            if strippedtype == idtype:
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
        no_ids = [
            link.link
            for link in auq.links
            if (link.type.startswith("!") and link.type[1:] == idtype)
        ]

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

            aliases = {*author.aliases, author.name} - {aname}

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
                yield author, p, no_ids


@bear
async def app(page):
    """Include/Exclude author Ids."""
    page["head"].print(
        H.link(rel="stylesheet", href=here.parent / "default.css")
    )

    author_name = page.query_params.get("author")

    def confirm_id(auth, confirmed, auth_id):
        link = auth.links[0].link
        type = auth.links[0].type

        id_linked = is_linked(link, type, author_name)

        if not confirmed:
            type = "!" + auth.links[0].type

        if not id_linked:
            db.insert_author_link(auth_id, type, link)
        elif id_linked.type != type:
            db.update_author_type(auth_id, type, link)

        # Modify the page
        page["#authoridbuttonarea" + link].clear()
        page["#authoridbuttonarea" + link].print_html(
            get_buttons(auth, auth_id, confirmed)
        )
        page["#idstatus" + link].clear()
        if confirmed:
            page["#idstatus" + link].print("ID Included")
        else:
            page["#idstatus" + link].print("ID Excluded")

    # Verify if the link is already linked to the author, included or excluded, with the same type.
    def is_linked(link, type, author_name):
        already_linked = get_links(type, author_name)
        for links in already_linked:
            if link in links.link:
                return links
        return False

    def get_links(type, author_name):
        author = get_authors(author_name)[0]
        links = []
        for link in author.links:
            strippedtype = (
                link.type[1:] if link.type.startswith("!") else link.type
            )
            if strippedtype == type:
                links.append(link)
        return links

    def get_authors(name):
        authors = []
        stmt = select(sch.Author).filter(sch.Author.name.like(f"%{name}%"))
        try:
            results = list(db.session.execute(stmt))
            for (r,) in results:
                authors.append(r)
        except Exception as e:
            print("Error : ", e)
        return authors

    def get_buttons(auth, author_id, included=None):
        includeButton = H.button["button"](
            "Include ID",
            onclick=(
                lambda event, auth=auth, author_id=author_id: confirm_id(
                    auth, 1, author_id
                )
            ),
        )
        excludeButton = H.button["button", "invalidate"](
            "Exclude ID",
            onclick=(
                lambda event, auth=auth, author_id=author_id: confirm_id(
                    auth, 0, author_id
                )
            ),
        )
        if included is not None:
            if included:
                includeButton = H.button["button", "notavailable"](
                    "Include ID",
                )
            else:
                excludeButton = H.button["button", "notavailable"](
                    "Exclude ID",
                )
        buttons = [includeButton, excludeButton]
        return buttons

    with load_config(os.environ["PAPERONI_CONFIG"]) as cfg:
        with cfg.database as db:
            reaserchers = get_authors(author_name)
            author_id = reaserchers[0].author_id
            tabIDS = []

            results = prepare(
                researchers=reaserchers,
                idtype="semantic_scholar",
                query_name=ss.author_with_papers,
            )
            async for auth, result, no_ids in results:
                link = auth.links[0].link
                if link not in tabIDS:
                    tabIDS.append(link)
                    author_name_area = H.div["authornamearea"](
                        H.p(auth.name),
                        H.p(auth.links[0].type),
                        H.a["link"](
                            link,
                            href="https://www.semanticscholar.org/author/"
                            + auth.name
                            + "/"
                            + str(link),
                            target="_blank",
                        ),
                        H.div["IDstatus"](id="idstatus" + link),
                        H.div["authoridbuttonarea"](
                            id="authoridbuttonarea" + link
                        ),
                    )

                    papers_area = H.div["papersarea"](id="a" + link)

                    area = H.div["authorarea"](
                        author_name_area,
                        papers_area,
                    )(id="area" + link)

                    page.print(area)

                    linked = is_linked(link, "semantic_scholar", author_name)
                    if linked != False:
                        is_excluded = link in no_ids
                        page["#authoridbuttonarea" + link].print_html(
                            get_buttons(
                                auth,
                                author_id,
                                not is_excluded,
                            )
                        )
                        if is_excluded:
                            page["#idstatus" + link].print("ID Excluded")
                        else:
                            page["#idstatus" + link].print("ID Included")
                    else:
                        page["#authoridbuttonarea" + link].print_html(
                            get_buttons(auth, author_id)
                        )

                div = html(result)
                valDiv = H.div["validationDiv"](div)
                aid = "#a" + link
                page[aid].print(valDiv)

            # Keep the app running
            while True:
                await asyncio.sleep(1)


ROUTES = app
