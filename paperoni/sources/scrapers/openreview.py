from collections import defaultdict
from datetime import datetime
import json
import re

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
from ..utils import prepare


class OpenReviewScraper:
    def __init__(self):
        self.client = openreview.Client(baseurl="https://api.openreview.net")

    @staticmethod
    def _map_venue_type(venueid):
        for v_type in VenueType:
            if v_type in venueid.lower():
                return v_type
        else:
            return VenueType.unknown

    def _query(self, params, total=0, limit=1000000):
        next_offset = 0
        while total < limit:
            params["offset"] = next_offset
            notes = self.client.get_all_notes(**params)
            for note in notes:
                if "venue" not in note.content:
                    continue
                authors = []
                if len(note.content["authors"]) == len(
                    note.content.get("authorids", [])
                ) and all(
                    (
                        aid is None or aid.startswith("~")
                        for aid in note.content["authorids"]
                    )
                ):
                    authors_ids = note.content["authorids"]
                else:
                    authors_ids = (
                        None for _ in range(len(note.content["authors"]))
                    )
                for name, author_id in zip(
                    note.content["authors"], authors_ids
                ):
                    _links = []
                    if author_id:
                        _links.append(
                            Link(
                                type="openreview", link=author_id or f"/{name}"
                            )
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
                                type=OpenReviewScraper._map_venue_type(
                                    note.content["venueid"]
                                ),
                                name=re.sub(
                                    pattern=" 2[0-9]{3} ",
                                    string=note.content["venue"],
                                    repl=" ",
                                ),
                                links=[],
                            ),
                            date=str(
                                datetime.fromtimestamp(note.tcdate / 1000)
                            ),
                            date_precision=DatePrecision.day,
                            volume=note.content["venueid"],
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

    def _query_all_venues(self, params, venues=None, total=0, limit=1000000):
        if not venues:
            venues = self.client.get_group(id="venues").members

        for v in venues:
            print(f"Fetching from venue {v}")
            params = {
                **params,
                "content": {**params["content"], "venueid": v},
            }

            for paper in self._query(params, total, limit):
                total += 1
                yield paper

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

        yield from self._query_all_venues(params, venue, 0, limit)

    @tooled
    def acquire(self, queries):
        todo = {}

        for auq in queries:
            for link in auq.author.links:
                if link.type == "openreview":
                    todo[link.link] = auq

        for author_id, auq in todo.items():
            print(f"Fetch papers for {auq.author.name} (id={author_id})")
            params = {
                "content": {"authorids": [author_id]},
                "mintcdate": int(auq.start_date.timestamp() * 1000),
            }
            for paper in self._query(params):
                yield paper
            break

    @tooled
    def prepare(self, researchers):
        # Venue on the basis of which to search
        venue: Option = None

        papers = list(
            self._query_all_venues(params={}, venues=venue and [venue])
        )

        def query_name(aname):
            print(f"Processing {aname}")
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

        return prepare(researchers, idtype="openreview", query_name=query_name)

    @tooled
    def venues(self):
        client = openreview.Client(baseurl="https://api.openreview.net")
        for venue in client.get_group(id="venues").members:
            yield venue


__scrapers__ = {"openreview": OpenReviewScraper()}
