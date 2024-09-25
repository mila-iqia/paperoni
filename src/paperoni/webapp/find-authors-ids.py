from datetime import datetime
from pathlib import Path

from hrepr import H
from sqlalchemy import select
from starbear import Queue, Reference

from ..config import papconf
from ..db import schema as sch
from ..sources.scrapers.openreview import OpenReviewPaperScraper
from ..sources.scrapers.semantic_scholar import SemanticScholarQueryManager
from ..utils import similarity
from .common import mila_template
from .render import paper_html

here = Path(__file__).parent

ss = SemanticScholarQueryManager()


async def prepare(
    researchers,
    query_name,
    cutoff=None,
    minimum=None,
):
    for auq in researchers:
        aname = auq.name
        data = [
            (author, similarity(aname, author.name), papers)
            for author, papers in query_name(aname)
            if not minimum or len(papers) > minimum
        ]
        data.sort(key=lambda ap: (-ap[1], -len(ap[-1])))
        for author, _, papers in data:
            if not papers:  # pragma: no cover
                continue
            papers = [
                (date.year, i, p)
                for i, p in enumerate(papers)
                if cutoff is None or (date := p.releases[0].venue.date) > cutoff
            ]
            papers.sort(reverse=True)
            for _, _, p in papers:
                yield author, p


@mila_template(title="Find author IDs", help="/help#find-author-ids")
async def __app__(page, box):
    """Include/Exclude author Ids."""
    author_id = bytes.fromhex(page.query_params.get("author_id"))
    cutoff = page.query_params.get("cutoff")
    cutoff = cutoff and datetime.strptime(cutoff, "%Y-%m-%d")

    scraper = page.query_params.get("scraper")
    action_q = Queue().wrap(refs=True)

    def get_links(type, author):
        q = """
        SELECT scrape_id, active FROM author_scrape_ids
        WHERE scraper = :scraper
        AND author_id = :author_id
        """
        results = db.session.execute(
            q, {"author_id": author.author_id, "scraper": type}
        )
        return dict(list(results))

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
            query_name=current_query_name,
            cutoff=cutoff,
        )
        num_results = 0
        async for auth, result in results:
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
                existing_links = get_links(scraper, the_author)
                status = existing_links.get(link, 0)
                page["#authoridbuttonarea" + link].print(
                    get_buttons(link, {-1: False, 0: None, 1: True}[status])
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
                    db.insert_author_scrape(
                        author_id, scraper, link, validity=1
                    )
                case "invalid":
                    db.insert_author_scrape(
                        author_id, scraper, link, validity=-1
                    )
                case "unknown":
                    db.insert_author_scrape(
                        author_id, scraper, link, validity=0
                    )

            page[result.ref].exec(
                f"this.setAttribute('status', '{result.tag}')"
            )


__app__.hidden = True
