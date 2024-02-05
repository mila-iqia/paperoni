from collections import Counter
from pathlib import Path

from giving import give
from hrepr import H
from sqlalchemy import select
from starbear import Queue, Reference

from ..config import papconf
from ..db import schema as sch
from ..sources.scrapers.openreview import OpenReviewPaperScraper
from ..sources.scrapers.semantic_scholar import SemanticScholarQueryManager
from .common import mila_template
from .render import paper_html

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


@mila_template(title="Find author IDs", help="/help#find-author-ids")
async def app(page, box):
    """Include/Exclude author Ids."""
    author_id = bytes.fromhex(page.query_params.get("author_id"))
    scraper = page.query_params.get("scraper")
    action_q = Queue().wrap(refs=True)

    # Verify if the link is already linked to the author, included or excluded, with the same type.
    def is_linked(link, type, author):
        already_linked = get_links(type, author)
        for links in already_linked:
            if link in links.link:
                return links
        return False

    def get_links(type, author):
        links = []
        for link in author.links:
            strippedtype = (
                link.type[1:] if link.type.startswith("!") else link.type
            )
            if strippedtype == type:
                links.append(link)
        return links

    def get_buttons(link, included=None):
        match included:
            case 0:
                existing_status = "invalid"
            case 1:
                existing_status = "valid"
            case _:
                existing_status = "unknown"

        val_div = H.div["validation-buttons"](
            H.div(
                H.button["valid"](
                    "Yes",
                    # Events put into action_q.tag("valid") will have
                    # event.tag == "valid", this is how we know which button
                    # was pressed.
                    onclick=action_q.tag("valid"),
                ),
                H.button["invalid"](
                    "No",
                    onclick=action_q.tag("invalid"),
                ),
                H.button["unknown"](
                    "Unknown",
                    onclick=action_q.tag("unknown"),
                ),
            ),
            # This property is used for styling, see the stylesheet
            status=existing_status,
            __ref=Reference(link),
        )
        return val_div

    def filter_link(link):  # For html elements
        filtered_link = link.replace("~", "")
        return filtered_link

    # Query name for openreview
    def query_name(aname):
        papers = list(
            or_scraper._query_papers_from_venues(
                params={"content": {}},
                venues=or_scraper._venues_from_wildcard(venue),
            )
        )
        results = {}
        for paper in papers:
            for pa in paper.authors:
                au = pa.author
                if au.name == aname:
                    for lnk in au.links:
                        if lnk.type == "openreview":
                            results.setdefault(lnk.link, (au, []))
                            results[lnk.link][1].append(paper)
        for auid, (au, aupapers) in results.items():
            yield (au, aupapers)

    async def select_venue(event):
        nonlocal venue
        venue = event["value"]
        await build_page("openreview")

    async def build_page(scraper):
        for i in tabIDS:
            page["#area" + i].delete()
            page["#authorarea" + i].delete()
            tabIDS.remove(i)
        page["#noresults"].delete()
        results = prepare(
            researchers=[the_author],
            idtype=scraper,
            query_name=current_query_name,
        )
        num_results = 0
        async for auth, result, no_ids in results:
            num_results += 1
            link = filter_link(auth.links[0].link)
            olink = auth.links[0].link
            if link not in tabIDS:
                tabIDS.append(link)
                if scraper == "semantic_scholar":
                    author_siteweb = (
                        "https://www.semanticscholar.org/author/"
                        + auth.name
                        + "/"
                        + str(link)
                    )
                elif scraper == "openreview":
                    author_siteweb = "https://openreview.net/profile?id=" + str(
                        olink
                    )
                author_name_area = H.div["authornamearea"](
                    H.p(auth.name),
                    H.p(auth.links[0].type),
                    H.a["link"](
                        olink,
                        href=author_siteweb,
                        target="_blank",
                    ),
                    H.div["IDstatus"](id="idstatus" + link),
                    H.div["authoridbuttonarea"](id="authoridbuttonarea" + link),
                )
                papers_area = H.div["papersarea"](id="a" + link)
                area = H.div["authorarea"](
                    author_name_area,
                    papers_area,
                )(id="area" + link)
                box.print(area)
                linked = is_linked(link, scraper, the_author)
                page["#authoridbuttonarea" + link].print(
                    get_buttons(
                        link,
                        None if linked is False else (link not in no_ids),
                    )
                )

            div = paper_html(result)
            valDiv = H.div["validationDiv"](div)
            aid = str("#a" + link)
            page[aid].print(valDiv)
        if num_results == 0:
            box.print(H.div["authorarea"]("No results found")(id="noresults"))
        print(num_results)

    with papconf.database as db:
        author_query = select(sch.Author).filter(
            sch.Author.author_id == author_id
        )
        the_author = list(db.session.execute(author_query))[0][0]
        tabIDS = []
        current_query_name = ss.author_with_papers
        if scraper == "semantic_scholar":
            current_query_name = ss.author_with_papers
        elif scraper == "openreview":
            or_scraper = OpenReviewPaperScraper(papconf, db)
            all_venues = or_scraper._venues_from_wildcard("*")
            current_query_name = query_name

            optionTab = []
            for venue in all_venues:
                optionTab.append(H.option[venue](venue))
            dropdown = H.select["venuedropdown"](
                optionTab,
                onchange=(
                    lambda event, author_id=author_id: select_venue(event)
                ),
                label="Select a venue",
            )
            box.print("Venues : ")
            box.print(dropdown)
        await build_page(scraper)

        async for result in action_q:
            link = result.obj
            match result.tag:
                case "valid":
                    db.insert_author_link(author_id, scraper, link, validity=1)
                case "invalid":
                    db.insert_author_link(author_id, scraper, link, validity=0)
                case "unknown":
                    db.insert_author_link(
                        author_id, scraper, link, validity=None
                    )

            page[result.ref].do(f"this.setAttribute('status', '{result.tag}')")


app.hidden = True

ROUTES = app
