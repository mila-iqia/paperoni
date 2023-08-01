from datetime import datetime

from coleo import Option, tooled
from sqlalchemy import or_, select

from .config import get_config
from .db import schema as sch


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
    title: Option = None,
    author: Option = None,
    author_link: Option = None,
    venue: Option = None,
    venue_link: Option = None,
    link: Option = None,
    start: Option = None,
    end: Option = None,
    year: Option & int = 0,
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
        stmt = stmt.join(sch.Paper.paper_author).join(
            sch.PaperAuthor.author
        )
    if author:
        stmt = stmt.join(sch.Author.author_alias).filter(
            likefmt(sch.AuthorAlias.alias, author)
        )
    if author_link:
        atyp, alnk = author_link.split(":")
        stmt = stmt.join(sch.Author.author_link).filter(
            sch.AuthorLink.type == atyp, sch.AuthorLink.link == alnk
        )
    if venue or venue_link or start or end:
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
    if link:
        stmt = stmt.join(sch.Paper.paper_link).filter(
            likefmt(sch.PaperLink.link, link)
        )
    stmt = stmt.group_by(sch.Paper.paper_id)
    return stmt
    
@tooled
def query_papers(
    title: Option = None,
    author: Option = None,
    author_link: Option = None,
    venue: Option = None,
    venue_link: Option = None,
    link: Option = None,
    start: Option = None,
    end: Option = None,
    year: Option & int = 0,
):
    cfg = get_config()
    with cfg.database as db:
        stmt = search_stmt(title, author, author_link, venue, venue_link, link, start, end, year)

        for (paper,) in db.session.execute(stmt):
            yield paper
