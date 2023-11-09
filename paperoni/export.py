from ovld import ovld

from .db import schema as sch
from .display import expand_links
from .model import DatePrecision
from .utils import peer_reviewed_release


def sort_releases(releases):
    releases = [
        (release, peer_reviewed_release(release)) for release in releases
    ]
    releases.sort(key=lambda entry: -int(entry[1]))
    return releases


@ovld
def export(paper: sch.Paper):
    return {
        "__type__": "Paper",
        "id": paper.paper_id.hex(),
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": [export(author) for author in paper.authors],
        "releases": [
            export(*release) for release in sort_releases(paper.releases)
        ],
        "topics": [export(topic) for topic in paper.topics],
        "links": [
            {"type": type, "url": url}
            for type, url in expand_links(paper.links)
        ],
        "citation_count": 0,
    }


@ovld
def export(paper_author: sch.PaperAuthor):
    return {
        "author": export(paper_author.author),
        "affiliations": [export(aff) for aff in paper_author.affiliations],
    }


@ovld
def export(institution: sch.Institution):
    return {
        "id": institution.institution_id.hex(),
        "name": institution.name,
        "category": institution.category,
    }


@ovld
def export(author: sch.Author):
    return {
        "id": author.author_id.hex(),
        "name": author.name,
        "links": [export(lnk) for lnk in author.links],
    }


@ovld
def export(link: (sch.PaperLink, sch.AuthorLink, sch.VenueLink)):
    return {
        "type": link.type,
        "link": link.link,
    }


@ovld
def export(topic: sch.Topic):
    return {
        "name": topic.name,
    }


@ovld
def export(release: sch.Release, peer_reviewed: bool):
    venue = release.venue
    return {
        "venue_id": venue.venue_id.hex(),
        "name": venue.name,
        "type": venue.type,
        "peer_reviewed": peer_reviewed,
        "date": DatePrecision.format(
            date=venue.date, precision=venue.date_precision
        ),
        "date_timestamp": venue.date,
        "date_precision": venue.date_precision,
        "status": release.status,
        "links": [export(lnk) for lnk in venue.links],
        "aliases": [a.alias for a in venue.venue_alias],
        "open": venue.open,
        "publisher": venue.publisher,
        "series": venue.series or "",
        "volume": venue.volume,
        "pages": release.pages,
    }
