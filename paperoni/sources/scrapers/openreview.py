import re
import sys
import time
from datetime import datetime, timedelta
from fnmatch import fnmatch

import openreview
from coleo import Option, tooled

from ...model import (
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
from ...tools import extract_date
from ..utils import prepare_interface, prompt_controller
from .base import BaseScraper


def venue_to_series(venueid):
    return re.sub(pattern=r"/[0-4]{4}", string=venueid, repl="")


def parse_openreview_venue(venue):
    extractors = {
        r"\b(2[0-9]{3})\b": "year",
        r"\b(submitted|poster|oral|spotlight)\b": "status",
    }
    results = {}
    for regexp, field in extractors.items():
        if m := re.search(pattern=regexp, string=venue, flags=re.IGNORECASE):
            results[field] = m.groups()[0].lower()
            start, end = m.span()
            venue = venue[:start] + venue[end:]
    results["venue"] = re.sub(pattern=r"[ ]+", repl=" ", string=venue).strip()
    return results


class OpenReviewScraperBase(BaseScraper):
    def __init__(self, config, db):
        super().__init__(config=config, db=db)
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
                if "venueid" not in note.content or note.content[
                    "venueid"
                ].startswith("dblp.org"):
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

                venue_data = parse_openreview_venue(note.content["venue"])
                date = datetime.fromtimestamp(note.tcdate // 1000)
                date -= timedelta(
                    hours=date.hour, minutes=date.minute, seconds=date.second
                )
                precision = DatePrecision.day
                if "year" in venue_data:
                    # Make sure that the year is correct
                    year = int(venue_data["year"])
                    if date.year != year:
                        date = datetime(year, 1, 1)
                        precision = DatePrecision.year
                    venue_data["venue"] += f" {year}"

                vid = note.content["venueid"]

                yield Paper(
                    title=note.content["title"],
                    abstract=note.content.get("abstract"),
                    authors=authors,
                    releases=[
                        Release(
                            venue=Venue(
                                type=OpenReviewScraperBase._map_venue_type(vid),
                                name=vid,
                                series=venue_to_series(vid),
                                volume=venue_data["venue"],
                                date=date,
                                date_precision=precision,
                                links=[
                                    Link(
                                        type="openreview-venue",
                                        link=vid,
                                    )
                                ],
                                aliases=[],
                            ),
                            status=venue_data.get("status", "published"),
                            pages=None,
                        )
                    ],
                    topics=[
                        Topic(name=kw)
                        for kw in note.content.get("keywords", [])
                    ],
                    links=_links,
                    citation_count=None,
                )
            next_offset += len(notes)
            if not notes:
                break
        total += next_offset

    def _query_papers_from_venues(
        self, params, venues=None, total=0, limit=1000000
    ):
        if not venues:
            venues = self.client.get_group(id="venues").members

        for v in venues:
            if v is not None:
                print(f"Fetching from venue {v}")
                params = {
                    **params,
                    "content": {**params["content"], "venueid": v},
                }

            for paper in self._query(params, total, limit):
                total += 1
                yield paper

    def _query_venues(self, venues):
        patterns = {
            "date": [
                r"(['\"]?)date\1: *(['\"])([^'\"]*)\2",
                r"(['\"]?)location\1: *(['\"])([^'\"]*)\2",
            ],
            "title": [
                r"(['\"]?)title\1: *(['\"])([^'\"]*)\2",
            ],
        }

        for venueid in venues:
            print(f"Query {venueid}")
            try:
                data = self.client.get_group(id=venueid)
            except openreview.OpenReviewException:
                print(f"Cannot view {venueid}", file=sys.stderr)
                continue

            info = {}
            for key, patts in patterns.items():
                for p in patts:
                    if m := re.search(pattern=p, string=data.web):
                        info[key] = m.groups()[2]
                        break
                else:
                    info[key] = None

            xdate = (
                extract_date(info.get("date"))
                or extract_date(info.get("location"))
                or extract_date(info.get("title"))
            )
            title = info.get("title")
            if not xdate or not title:
                continue

            yield Venue(
                type=self._map_venue_type(venueid),
                name=title,
                series=venue_to_series(venueid),
                aliases=[],
                links=[Link(type="openreview-venue", link=venueid)],
                quality=(1.0,),
                **xdate,
            )


class OpenReviewPaperScraper(OpenReviewScraperBase):
    @tooled
    def query(
        self,
        # Author to query
        # [alias: -a]
        # [nargs: +]
        author: Option = [],
        # Author ID to query
        # [alias: --aid]
        author_id: Option = [],
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
        if author_id:
            params = {
                **params,
                "content": {**params["content"], "authorids": [author_id]},
            }
            if not venue:
                venue = [None]
        if title:
            params = {
                **params,
                "content": {**params["content"], "title": title},
            }

        yield from self._query_papers_from_venues(params, venue, 0, limit)

    @tooled
    def acquire(self):
        queries = self.generate_paper_queries()

        todo = {}

        for auq in queries:
            for link in auq.author.links:
                if link.type == "openreview":
                    todo[link.link] = auq

        for author_id, auq in todo.items():
            print(f"Fetch papers for {auq.author.name} (id={author_id})")
            time.sleep(5)
            params = {
                "content": {"authorids": [author_id]},
                "mintcdate": int(auq.start_date.timestamp() * 1000),
            }
            for paper in self._query(params):
                yield paper

    @tooled
    def prepare(self, controller=prompt_controller):
        # Venue on the basis of which to search
        venue: Option = None

        _papers = None

        def query_name(aname):
            nonlocal _papers
            if _papers is None:
                papers = list(
                    self._query_papers_from_venues(
                        params={"content": {}}, venues=venue and [venue]
                    )
                )

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

        return prepare_interface(
            researchers=self.generate_author_queries(),
            idtype="openreview",
            query_name=query_name,
            controller=controller,
        )


class OpenReviewVenueScraper(OpenReviewScraperBase):
    @tooled
    def query(
        self,
        # Pattern for the conferences to query
        pattern: Option = "*",
    ):
        members = self.client.get_group(id="venues").members
        members = [
            member
            for member in members
            if fnmatch(pat=pattern, name=member.lower())
        ]
        yield from self._query_venues(members)

    @tooled
    def acquire(self):
        yield from self.query()

    @tooled
    def prepare(self):
        print("TODO")


__scrapers__ = {
    "openreview": OpenReviewPaperScraper,
    "openreview-venues": OpenReviewVenueScraper,
}
