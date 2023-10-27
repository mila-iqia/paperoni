from ovld import ovld

from ..cli_helper import ExtendAttr
from .. import model as M
from . import schema as sch


@ovld
def export(paper: sch.Paper):
    return M.Paper(
        title=paper.title,
        abstract=paper.abstract,
        authors=[export(author) for author in paper.authors],
        releases=[export(release) for release in paper.releases],
        topics=[export(topic) for topic in paper.topics],
        links=[export(link) for link in paper.links],
        quality=0,
        citation_count=0,
    )


@ovld
def export(paper_author: sch.PaperAuthor):
    return M.PaperAuthor(
        author=export(paper_author.author),
        affiliations=[export(aff) for aff in paper_author.affiliations],
    )


@ovld
def export(institution: sch.Institution):
    return M.Institution(
        name=institution.name,
        aliases=institution.aliases,
        category=institution.category,
    )


@ovld
def export(author: sch.Author):
    return M.Author(
        name=author.name,
        aliases=author.aliases,
        links=[export(lnk) for lnk in author.links],
        quality=author.quality,
        roles=[],
    )


@ovld
def export(link: (sch.PaperLink, sch.AuthorLink, sch.VenueLink)):
    return M.Link(
        type=link.type,
        link=link.link,
    )


@ovld
def export(topic: sch.Topic):
    return M.Topic(
        name=topic.name,
    )


@ovld
def export(release: sch.Release):
    return M.Release(
        venue=export(release.venue),
        pages=release.pages,
        status=release.status,
    )


@ovld
def export(venue: sch.Venue):
    return M.Venue(
        name=venue.name,
        type=venue.type,
        date=venue.date,
        date_precision=venue.date_precision,
        links=[export(lnk) for lnk in venue.links],
        aliases=[a.alias for a in venue.venue_alias],
        open=venue.open,
        peer_reviewed=venue.peer_reviewed,
        publisher=venue.publisher,
        series=venue.series or "",
        volume=venue.volume,
        quality=venue.quality,
    )


@ovld
def export(extattr: ExtendAttr):
    return export(extattr._search_result)
