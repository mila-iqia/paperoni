from datetime import datetime

import openreview
from coleo import Option, tooled

from ..model import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    Venue,
    VenueType,
)


class OpenReviewScraper:
    @tooled
    def query(
        self,
        # Author to query
        # [alias: -a]
        # [nargs: +]
        author: Option = [],
        # Title of the paper
        # [alias: -t]
        # [nargs: +]
        title: Option = [],
        # Maximal number of results per query
        block_size: Option & int = 1000,
        # Maximal number of results to return
        limit: Option & int = 10000,
        # Venue of the paper
        # [alias: -v]
        # [nargs: +]
        venue: Option = [],
    ):
        author = " ".join(author)
        title = " ".join(title)

        client = openreview.Client(baseurl="https://api.openreview.net")
        params = {
            "content": {},
            "limit": min(block_size or limit, limit),
            "offset": 0,
        }
        if author:
            params = {
                **params,
                "content": {**params["content"], "authors": [author]},
            }
        if title:
            params = {
                **params,
                "content": {**params["content"], "title": title},
            }
        if not venue:
            venue = client.get_group(id="venues").members

        total = 0
        for v in venue:
            params = {
                **params,
                "content": {**params["content"], "venueid": v},
            }

            for v_type in VenueType:
                if v_type in v.lower():
                    venue_type = v_type
                    break
            else:
                venue_type = VenueType.unknown

            next_offset = 0
            while total < limit:
                params["offset"] = next_offset
                notes = client.get_all_notes(**params)
                for note in notes:
                    authors = []
                    authors_ids = note.content.get(
                        "authorids",
                        (None for _ in range(len(note.content["authors"]))),
                    )
                    authors_emails = note.content.get(
                        "author_emails",
                        (None for _ in range(len(note.content["authors"]))),
                    )
                    for name, author_id, authors_email in zip(
                        note.content["authors"], authors_ids, authors_emails
                    ):
                        _links = []
                        if author_id:
                            _links.append(
                                Link(type="openreview", link=author_id)
                            )
                        if authors_email:
                            _links.append(
                                Link(type="email", link=authors_email)
                            )
                        authors.append(
                            PaperAuthor(
                                affiliations=[],
                                author=Author(
                                    name=name,
                                    affiliations=[],
                                    aliases=[],
                                    links=_links,
                                    roles=[],
                                ),
                            )
                        )
                    _links = [Link(type="openreview", link=note.id)]
                    if "code" in note.content:
                        Link(type="git", link=note.content["code"])
                    yield Paper(
                        title=note.content["title"],
                        abstract=note.content.get("abstract", ""),
                        citation_count=0,
                        authors=authors,
                        releases=[
                            Release(
                                venue=Venue(
                                    type=venue_type,
                                    name=note.content["venue"],
                                    links=[],
                                ),
                                date=str(
                                    datetime.fromtimestamp(note.tcdate / 1000)
                                ),
                                date_precision=DatePrecision.day,
                            )
                        ],
                        topics=[
                            Topic(name=kw)
                            for kw in note.content.get("keywords", [])
                        ],
                        links=_links,
                        scrapers=["orev"],
                    )
                next_offset += len(notes)
                if not notes:
                    break
            total += next_offset

    @tooled
    def acquire(self, queries):
        pass

    @tooled
    def prepare(self, researchers):
        pass

    @tooled
    def venues(self):
        client = openreview.Client(baseurl="https://api.openreview.net")
        for venue in client.get_group(id="venues").members:
            yield venue


__scrapers__ = {"openreview": OpenReviewScraper()}
