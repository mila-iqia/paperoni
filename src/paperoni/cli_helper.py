import re
from datetime import datetime
from typing import Any

from coleo import Option, tooled
from sqlalchemy import or_, select

from .config import papconf
from .db import schema as sch
from .fulltext.download import PDF, CachePolicies, fulltext


@tooled
def timespan(timestamp=False):
    start: Option = None
    end: Option = None
    year: Option & int = 0

    if year:
        assert not start
        assert not end
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

    if timestamp:
        return (
            start and int(datetime(*map(int, start.split("-"))).timestamp()),
            end and int(datetime(*map(int, end.split("-"))).timestamp()),
        )
    else:
        return start, end


def _timespan(start=None, end=None, year=0, timestamp=False):
    if year:
        assert not start
        assert not end
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

    if timestamp:
        return (
            start and int(datetime(*map(int, start.split("-"))).timestamp()),
            end and int(datetime(*map(int, end.split("-"))).timestamp()),
        )
    else:
        return start, end


def search_stmt(
    title=None,
    author=None,
    author_link=None,
    affiliation=None,
    venue=None,
    venue_link=None,
    link=None,
    start=None,
    end=None,
    year=0,
    topic=None,
    sort=None,
    flags=[],
):
    start, end = _timespan(start, end, year, timestamp=True)

    def likefmt(field, x):
        if x.startswith("="):
            return field == x[1:]
        else:
            return field.like(f"%{x}%")

    stmt = select(sch.Paper)
    if title:
        stmt = stmt.filter(likefmt(sch.Paper.title, title))
    if author or author_link:
        stmt = stmt.join(sch.Paper.paper_author).join(sch.PaperAuthor.author)
    if author:
        stmt = stmt.join(sch.Author.author_alias).filter(
            likefmt(sch.AuthorAlias.alias, author)
        )
    if author_link:
        atyp, alnk = author_link.split(":")
        stmt = stmt.join(sch.Author.author_link).filter(
            sch.AuthorLink.type == atyp, sch.AuthorLink.link == alnk
        )
    if affiliation:
        stmt = (
            stmt.join(sch.Paper.paper_author_institution)
            .join(sch.PaperAuthorInstitution.institution)
            .join(sch.Institution.institution_alias)
            .filter(likefmt(sch.InstitutionAlias.alias, affiliation))
        )
    if venue or venue_link or start or end or (sort and "date" in sort):
        stmt = stmt.join(sch.Paper.release).join(sch.Release.venue)
    if venue:
        venues = [venue] if not isinstance(venue, list) else venue
        stmt = stmt.filter(
            or_(likefmt(sch.Venue.name, venue) for venue in venues)
        )
    if venue_link:
        stmt = stmt.join(sch.Venue.venue_link)
        stmt = stmt.filter(likefmt(sch.VenueLink.link, venue_link))
    if start:
        stmt = stmt.filter(sch.Venue.date >= start)
    if end:
        stmt = stmt.filter(sch.Venue.date <= end)
    if topic:
        stmt = stmt.join(sch.Paper.topic).filter(
            likefmt(sch.Topic.topic, topic)
        )
    if link:
        stmt = stmt.join(sch.Paper.paper_link).filter(
            likefmt(sch.PaperLink.link, link)
        )
    if flags:
        stmt = stmt.join(sch.Paper.paper_flag)
        for flag in flags:
            if flag.startswith("*"):
                # Flag has a value
                flag = flag.removeprefix("*")
                stmt = stmt.filter(sch.PaperFlag.flag_name == flag)
            elif flag.startswith("~"):
                # Flag does not have a value
                # BUT: does not work, unfortunately
                flag = flag.removeprefix("~")
                has_flag = (
                    select(sch.Paper.paper_id)
                    .join(sch.Paper.paper_flag)
                    .filter(sch.PaperFlag.flag_name == flag)
                )
                stmt = stmt.filter(sch.Paper.paper_id.not_in(has_flag))
            elif flag.startswith("!"):
                # Flag has value 0
                flag = flag.removeprefix("!")
                stmt = stmt.filter(
                    (sch.PaperFlag.flag_name == flag)
                    & (sch.PaperFlag.flag == 0)
                )
            else:
                # Flag has value 1
                stmt = stmt.filter(
                    (sch.PaperFlag.flag_name == flag)
                    & (sch.PaperFlag.flag == 1)
                )
    stmt = stmt.group_by(sch.Paper.paper_id)

    sort_column = None
    if sort is not None:
        desc = False
        if sort.startswith("-"):
            sort = sort[1:]
            desc = True
        match sort:
            case "date":
                sort_column = sch.Venue.date
            case _:
                raise Exception(f"Unknown sort: {sort}")
        if desc:
            sort_column = sort_column.desc()
        stmt = stmt.order_by(sort_column)

    return stmt


def find_excerpt(paper, excerpt, allow_download=True):
    text = fulltext(
        paper,
        cache_policy=CachePolicies.USE
        if allow_download
        else CachePolicies.NO_DOWNLOAD,
    )
    if text is None:
        return None
    match = re.search(string=text, pattern=excerpt, flags=re.IGNORECASE)
    if not match:
        return None
    start, end = match.span()
    context = 100
    return (
        text[max(0, start - context) : start],
        text[start:end],
        text[end : end + context],
    )


# TODO: move this to an utils file
# SQLAlchemy seams to reuse search results. Wrap that object to allow extentions
# of the object data without leaking them to other search results
class ExtendAttr:
    def __init__(self, search_result) -> None:
        self._search_result = search_result

    def __getattribute__(self, __name: str) -> Any:
        try:
            attr = super().__getattribute__(__name)
        except AttributeError:
            search_result = super().__getattribute__("_search_result")
            attr = search_result.__getattribute__(__name)
        return attr


def search(
    title=None,
    author=None,
    author_link=None,
    affiliation=None,
    venue=None,
    venue_link=None,
    link=None,
    start=None,
    end=None,
    year=0,
    topic=None,
    excerpt=None,
    allow_download=False,
    flags=[],
    filters=[],
    sort=None,
    db=None,
):
    def proceed(db):
        stmt = search_stmt(
            title=title,
            author=author,
            author_link=author_link,
            affiliation=affiliation,
            venue=venue,
            venue_link=venue_link,
            link=link,
            start=start,
            end=end,
            topic=topic,
            year=year,
            flags=flags,
            sort=sort,
        )

        for (paper,) in db.session.execute(stmt):
            paper = ExtendAttr(paper)
            if excerpt:
                ranges = find_excerpt(paper, excerpt, allow_download)
                if ranges is None:
                    continue
                paper.excerpt = ranges
            if all(f(paper) for f in filters):
                yield paper

    if db is None:
        with papconf.database as db:
            yield from proceed(db)
    else:
        yield from proceed(db)


@tooled
def query_papers(
    title: Option = None,
    author: Option = None,
    author_link: Option = None,
    affiliation: Option = None,
    venue: Option = None,
    venue_link: Option = None,
    link: Option = None,
    start: Option = None,
    end: Option = None,
    year: Option & int = 0,
    topic: Option = None,
    excerpt: Option & str = None,
    sort: Option & str = None,
    # [action: append]
    flag: Option & str = [],
    # [negate]
    allow_download: Option & bool = True,
):
    yield from search(
        title=title,
        author=author,
        author_link=author_link,
        affiliation=affiliation,
        venue=venue,
        venue_link=venue_link,
        link=link,
        start=start,
        end=end,
        year=year,
        topic=topic,
        excerpt=excerpt,
        allow_download=allow_download,
        flags=flag,
        sort=sort,
    )


def download_paper(paper):
    pdf = PDF(
        identifier=paper.paper_id.hex(),
        title=paper.title,
        refs=[f"{lnk.type}:{lnk.link}" for lnk in paper.links],
        cache_policy=CachePolicies.USE,
    )
    if pdf.get():
        print(f"Successfully downloaded PDF for '{paper.title}'")
    else:
        print(f"ERROR: Could not download PDF for '{paper.title}'")


@tooled
def download_papers(
    title: Option = None,
    author: Option = None,
    author_link: Option = None,
    affiliation: Option = None,
    venue: Option = None,
    venue_link: Option = None,
    link: Option = None,
    start: Option = None,
    end: Option = None,
    year: Option & int = 0,
    topic: Option = None,
    sort: Option & str = None,
    # [action: append]
    flag: Option & str = [],
):
    papers = search(
        title=title,
        author=author,
        author_link=author_link,
        affiliation=affiliation,
        venue=venue,
        venue_link=venue_link,
        link=link,
        start=start,
        end=end,
        year=year,
        topic=topic,
        flags=flag,
        sort=sort,
    )
    for p in papers:
        download_paper(p)
