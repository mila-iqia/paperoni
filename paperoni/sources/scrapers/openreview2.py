import re
import sys
import time
from datetime import datetime, timedelta
from fnmatch import fnmatch
from functools import reduce

import openreview
from coleo import Option, tooled

from paperoni.display import display

from ...config import papconf
from ...model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Meta,
    Paper,
    PaperAuthor,
    Release,
    Role,
    ScraperData,
    Topic,
    Venue,
    VenueType,
)
from ...utils import Doing, covguard, extract_date
from ..helpers import (
    filter_papers,
    filter_researchers_interface,
    prepare_interface,
    prompt_controller,
)
from .base import BaseScraper


def venue_to_series(venueid):
    return re.sub(pattern=r"/[0-4]{4}", string=venueid, repl="")


def parse_openreview_venue(venue):
    extractors = {
        r"\b(2[0-9]{3})\b": "year",
        r"\b(submitted|accepted|accept|notable|poster|oral|spotlight|withdrawn|rejected)\b": "status",
    }
    results = {}
    for regexp, field in extractors.items():
        if m := re.search(pattern=regexp, string=venue, flags=re.IGNORECASE):
            results[field] = m.groups()[0].lower()
            start, end = m.span()
            venue = venue[:start] + venue[end:]
    if results.get("status", None) == "submitted":
        results["status"] = "rejected"
    results["venue"] = re.sub(pattern=r"[ ]+", repl=" ", string=venue).strip()
    return results


class OpenReviewScraperBase(BaseScraper):
    def __init__(self, config, db):
        super().__init__(config=config, db=db)
        self.set_client()

    def set_client(self):
        self.client = openreview.Client(baseurl="https://api2.openreview.net")

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
                vid_container = note.content.get("venueid", None)
                vid = vid_container and vid_container["value"]
                if not vid or vid.startswith("dblp.org"):
                    continue
                if "authors" not in note.content:
                    continue
                authors = []
                if len(note.content["authors"]["value"]) == len(
                    note.content.get("authorids", {}).get("value", [])
                ) and all(
                    (
                        aid is None or aid.startswith("~")
                        for aid in note.content["authorids"]["value"]
                    )
                ):
                    authors_ids = note.content["authorids"]["value"]
                else:
                    authors_ids = (
                        None
                        for _ in range(len(note.content["authors"]["value"]))
                    )
                for name, author_id in zip(
                    note.content["authors"]["value"], authors_ids
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
                                quality=(0.75,),
                            ),
                        )
                    )
                _links = [Link(type="openreview", link=note.id)]
                if "code" in note.content:
                    Link(type="git", link=note.content["code"]["value"])

                venue_data = parse_openreview_venue(
                    note.content["venue"]["value"]
                )
                if "status" not in venue_data and note.pdate:
                    venue_data["status"] = "published"

                date = datetime.fromtimestamp(
                    (note.pdate or note.odate or note.tcdate or note.tmdate)
                    // 1000
                )
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

                yield Paper(
                    title=note.content["title"]["value"],
                    abstract=note.content.get("abstract", {}).get("value"),
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
                                quality=(0.5,),
                            ),
                            status=venue_data.get("status", "unknown"),
                            pages=None,
                        )
                    ],
                    topics=[
                        Topic(name=kw)
                        for kw in note.content.get("keywords", {}).get(
                            "value", []
                        )
                    ],
                    links=_links,
                    citation_count=None,
                )
            next_offset += len(notes)
            if not notes or "id" in params:
                break
        total += next_offset

    def _query_papers_from_venues(
        self, params, venues=None, total=0, limit=1000000
    ):
        if not venues:  # pragma: no cover
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
            with Doing(venue=venueid):
                print(f"Query {venueid}")
                try:
                    data = self.client.get_group(id=venueid)
                except openreview.OpenReviewException:
                    print(f"Cannot view {venueid}", file=sys.stderr)
                    continue

                if not data.web:
                    continue

                info = {}
                for key, patts in patterns.items():
                    for p in patts:
                        if m := re.search(pattern=p, string=data.web):
                            info[key] = m.groups()[2]
                            break
                    else:
                        # Currently covered with NeurIPS.cc/2023
                        with covguard():
                            info[key] = None

                xdate = (
                    extract_date(info.get("date"))
                    or extract_date(info.get("location"))
                    or extract_date(info.get("title"))
                )
                title = info.get("title")
                if not xdate or not title:
                    with covguard():
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

    def get_profile(self, authorid):
        def _position(entry):
            return (
                (entry.get("position") or "affiliated")
                .lower()
                .replace(" ", "_")
            )

        def _make_institution(entry):
            inst = entry["institution"]
            pos = _position(entry)

            category = InstitutionCategory.unknown
            if (
                "phd" in pos
                or "msc" in pos
                or "student" in pos
                or "professor" in pos
            ):
                category = InstitutionCategory.academia
            return Institution(
                name=inst["name"],
                category=category,
                aliases=[inst["domain"]] if inst.get("domain", None) else [],
            )

        def make_name(namedata):
            parts = [namedata["first"], namedata["middle"], namedata["last"]]
            parts = [p for p in parts if p]
            name = " ".join(parts)
            return namedata.get("preferred", False), name

        def _make_role(entry):
            start_date = (
                DatePrecision.make_date(entry.get("start"), alignment="start")
                or DatePrecision.make_date(entry.get("end"), alignment="start")
                or datetime(2000, 1, 1)
            )
            end_date = DatePrecision.make_date(
                entry.get("end"), alignment="end"
            )
            return Role(
                role=_position(entry),
                start_date=start_date,
                end_date=end_date,
                institution=_make_institution(entry),
            )

        data = self.client.get_profile(authorid)

        names = [make_name(x) for x in data.content.get("names", [])]
        names.sort(reverse=True)
        names = [n[1] for n in names]

        return Author(
            name=names[0],
            aliases=names[1:],
            links=[
                Link(type="openreview", link=name["username"])
                for name in data.content["names"]
                if "username" in name
            ],
            roles=[
                _make_role(entry) for entry in data.content.get("history", [])
            ],
            quality=0.0,
        )

    def _venues_from_wildcard(self, pattern):
        if isinstance(pattern, list):
            return reduce(
                list.__add__, [self._venues_from_wildcard(p) for p in pattern]
            )
        elif "*" not in pattern:
            return [pattern]
        else:
            members = self.client.get_group(id="venues").members
            return [
                member
                for member in members
                if fnmatch(pat=pattern.lower(), name=member.lower())
            ]


class OpenReviewPaperScraper(OpenReviewScraperBase):
    @tooled
    def query(
        self,
        # Author ID to query
        # [alias: --aid]
        author_id: Option = [],
        # Paper ID to query
        # [alias: --pid]
        paper_id: Option = [],
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
        title = " ".join(title)

        params = {
            "content": {},
            "limit": min(block_size or limit, limit),
            "offset": 0,
        }

        if paper_id:
            params = {
                **params,
                "id": paper_id,
            }
            if not venue:
                venue = [None]
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
        # Venue to fetch from
        # [alias: -v]
        # [nargs: +]
        venue: Option = None

        if venue:
            venues = self._venues_from_wildcard(venue)
            yield from self._query_papers_from_venues(
                params={"content": {}}, venues=venues
            )

        else:
            queries = self.generate_ids(scraper="openreview")
            queries = filter_researchers_interface(
                list(queries), getname=lambda row: row[0]
            )

            yield Meta(
                scraper="openreview",
                date=datetime.now(),
            )

            for name, ids, start, end in queries:
                for author_id in ids:
                    print(f"Fetch papers for {name} (ID={author_id})")
                    params = {
                        "content": {"authorids": [author_id]},
                        "mintcdate": int(start.timestamp() * 1000),
                    }
                    yield from filter_papers(
                        papers=self._query(params),
                        start=start,
                        end=end,
                    )
                    time.sleep(5)

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
                        params={"content": {}},
                        venues=self._venues_from_wildcard(venue),
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
        members = self._venues_from_wildcard(pattern)
        with papconf.permanent_request_cache():
            # Reset client because we are using a different requests.Session
            self.set_client()
            yield from self._query_venues(members)
        self.set_client()

    @tooled
    def acquire(self):
        yield from self.query()

    @tooled
    def prepare(self):  # pragma: no cover
        print("TODO")


class OpenReviewProfileScraper(OpenReviewScraperBase):
    @tooled
    def query(self, authorid: Option & str = None):
        assert authorid
        yield self.get_profile(authorid)

    @tooled
    def acquire(self):
        limit: Option & int = 1000

        with self.db as db:
            query = """
            SELECT DISTINCT link FROM author_link WHERE type = "openreview"
            EXCEPT
            SELECT link FROM author_link
                JOIN scraper_data ON tag = link
                WHERE scraper = "openreview-profiles"
                AND type = "openreview"
            """
            rows = db.session.execute(query)
            for row in list(rows)[:limit]:
                print(f"Acquiring {row.link}")
                for result in self.query(authorid=row.link):
                    display(result)
                    yield result
                    for lnk in result.links:
                        if lnk.type == "openreview":
                            yield ScraperData(
                                scraper="openreview-profiles",
                                tag=lnk.link,
                                date=datetime.now(),
                                data=None,
                            )
                time.sleep(0.5)

    @tooled
    def prepare(self):  # pragma: no cover
        print("TODO")


__scrapers__ = {
    "openreview2": OpenReviewPaperScraper,
    "openreview2-venues": OpenReviewVenueScraper,
    "openreview2-profiles": OpenReviewProfileScraper,
}
