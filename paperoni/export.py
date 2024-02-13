from ovld import ovld

from .cli_helper import ExtendAttr
from .db import schema as sch
from .model import DatePrecision
from .utils import expand_links_dict, peer_reviewed_release


def sort_releases(releases):
    releases = [
        (release, peer_reviewed_release(release)) for release in releases
    ]
    releases.sort(key=lambda entry: -int(entry[1]))
    return releases


@ovld
def export(paper: ExtendAttr):
    return {
        **export(paper._search_result),
        "excerpt": getattr(paper, "excerpt", None),
    }


@ovld
def export(paper: sch.Paper):
    return {
        "paper_id": paper.paper_id.hex(),
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": [export(author) for author in paper.authors],
        "releases": [
            export(*release) for release in sort_releases(paper.releases)
        ],
        "topics": [export(topic) for topic in paper.topics],
        "links": expand_links_dict(paper.links),
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
        "institution_id": institution.institution_id.hex(),
        "name": institution.name,
        "category": institution.category,
    }


@ovld
def export(author: sch.Author):
    return {
        "author_id": author.author_id.hex(),
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
    return {
        "venue": export(release.venue),
        "peer_reviewed": peer_reviewed,
        "status": release.status,
        "pages": release.pages,
    }


@ovld
def export(venue: sch.Venue):
    return {
        "venue_id": venue.venue_id.hex(),
        "name": venue.name,
        "type": venue.type,
        "date": {
            "text": DatePrecision.format(
                date=venue.date, precision=venue.date_precision
            ),
            "timestamp": venue.date,
            "precision": venue.date_precision,
        },
        "links": [export(lnk) for lnk in venue.links],
        "publisher": venue.publisher,
        "series": venue.series or "",
        "volume": venue.volume,
    }
