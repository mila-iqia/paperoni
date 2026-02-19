import re
import sys
from dataclasses import dataclass, field, field as dc_field
from datetime import date, datetime
from fnmatch import fnmatch
from functools import reduce

import gifnoc
import openreview
import openreview.api
from serieux.features.encrypt import Secret

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
from ..model.focus import Focus, Focuses
from .base import Discoverer


def extract_date(txt: str) -> dict | None:
    if isinstance(txt, int):
        return {
            "date": date(txt, 1, 1),
            "date_precision": DatePrecision.year,
        }

    if not isinstance(txt, str):
        return None

    # The dash just separates the 3-letter abbreviation from the rest of the month,
    # it is split immediately after that
    months = [
        "Jan-uary",
        "Feb-ruary",
        "Mar-ch",
        "Apr-il",
        "May-",
        "Jun-e",
        "Jul-y",
        "Aug-ust",
        "Sep-tember",
        "Oct-ober",
        "Nov-ember",
        "Dec-ember",
    ]
    months = [m.split("-") for m in months]
    stems = [a.lower() for a, b in months]
    months = [(f"{a}(?:{b})?\\.?" if b else a) for a, b in months]
    month = "|".join(months)  # This is a regexp like "Jan(uary)?|Feb(ruary)?|..."

    patterns = {
        # Jan 3-Jan 7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *(?:{month}) [0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3-7 2020
        rf"({month}) ([0-9]{{1,2}}) *- *[0-9]{{1,2}}[, ]+([0-9]{{4}})": (
            "m",
            "d",
            "y",
        ),
        # Jan 3 2020
        rf"({month}) ?([0-9]{{1,2}})[, ]+([0-9]{{4}})": ("m", "d", "y"),
        # 3-7 Jan 2020
        rf"([0-9]{{1,2}}) *- *[0-9]{{1,2}}[ ,]+({month})[, ]+([0-9]{{4}})": (
            "d",
            "m",
            "y",
        ),
        # 3 Jan 2020
        rf"([0-9]{{1,2}})[ ,]+({month})[, ]+([0-9]{{4}})": ("d", "m", "y"),
        # Jan 2020
        rf"({month}) +([0-9]{{4}})": ("m", "y"),
        # 2020 Jan 3
        rf"([0-9]{{4}}) ({month}) ([0-9]{{1,2}})": ("y", "m", "d"),
        # 2020 Jan
        rf"([0-9]{{4}}) ({month})": ("y", "m"),
        r"([0-9]{4})": ("y",),
    }

    for pattern, parts in patterns.items():
        if m := re.search(pattern=pattern, string=txt, flags=re.IGNORECASE):
            results = {k: m.groups()[i] for i, k in enumerate(parts)}
            precision = DatePrecision.day
            if "d" not in results:
                results.setdefault("d", 1)
                precision = DatePrecision.month
            if "m" not in results:
                results.setdefault("m", "Jan")
                precision = DatePrecision.year
            return {
                "date": date(
                    int(results["y"]),
                    stems.index(results["m"].lower()[:3]) + 1,
                    int(results["d"]),
                ),
                "date_precision": precision,
            }
    else:
        return None


def get_invitation(note):
    if hasattr(note, "invitation"):
        return note.invitation
    elif inv := getattr(note, "invitations", None):
        return inv[0]
    else:
        return "Unknown"


def venue_to_series(venueid):
    return re.sub(pattern=r"/[0-4]{4}", string=venueid, repl="")


def parse_openreview_venue(venue):
    extractors = {
        r"\b(2[0-9]{3})\b": "year",
        r"\b(submitted|accepted|accept|notable|poster|oral|spotlight|withdrawn|rejected)\b": "status",
    }
    results = {}
    for regexp, field_ in extractors.items():
        if m := re.search(pattern=regexp, string=venue, flags=re.IGNORECASE):
            results[field_] = m.groups()[0].lower()
            start, end = m.span()
            venue = venue[:start] + venue[end:]
    if results.get("status", None) == "submitted":
        results["status"] = "rejected"
    results["venue"] = re.sub(pattern=r"[ ]+", repl=" ", string=venue).strip()
    return results


@dataclass
class OpenReview(Discoverer):
    api_version: int = 2
    username: Secret[str] = None
    password: Secret[str] = None
    token: Secret[str] = field(default_factory=lambda: openreview_api_key)

    def __post_init__(self):
        self.set_client()

    def set_client(self):
        if self.api_version == 1:
            self.client = openreview.Client(
                baseurl="https://api.openreview.net",
                username=self.username,
                password=self.password,
                token=self.token,
            )
        elif self.api_version == 2:
            self.client = openreview.api.OpenReviewClient(
                baseurl="https://api2.openreview.net",
                username=self.username,
                password=self.password,
                token=self.token,
            )

    def get_content_field(self, note, key, default=None):
        content = note["content"] if isinstance(note, dict) else note.content
        if key not in content:
            return default
        v = content[key]
        match self.api_version:
            case 1:
                return v
            case 2:
                return v["value"]

    def get_venue_id(self, note):
        vid = self.get_content_field(note, "venueid")
        if not vid:
            vid = get_invitation(note).split("/-/")[0]
        if not vid or vid.startswith("dblp.org") or vid == "OpenReview.net/Archive":
            return None
        return vid

    def refine_decision(self, text):
        text = text.lower()
        patterns = {
            "notable": "notable",
            "poster": "poster",
            "oral": "oral",
            "spotlight": "spotlight",
            "withdraw": "withdrawn",
            "withdrawn": "withdrawn",
            "accepted": "accepted",
            "accept": "accepted",
            "reject": "rejected",
            "rejected": "rejected",
            "submitted": "rejected",
        }
        for key, decision in patterns.items():
            if key in text:
                return decision
        return None

    def figure_out_the_fking_decision(self, note):
        # heuristics = [(rank, invitation_regexp, content_field), ...]
        # rank: prioritize matching entries with a lower rank
        # invitation_regexp: pattern that the reply's invitation should match
        # field: field in which to find the decision, or if starting with =, the decision itself
        heuristics = [
            (5, ".*withdrawn?[^/]*$", "=withdrawn"),
            (10, ".*/decision$", "decision"),
            (20, ".*decision[^/]*$", "decision"),
            (30, ".*accept[^/]*$", "decision"),
            (40, ".*", "decision"),
            (40, ".*", "Decision"),
            (50, ".*meta_?review[^/]*$", "recommendation"),
        ]
        ranked_results = []
        for reply in reversed(note.details["replies"]):
            invitations = (
                [reply["invitation"]] if self.api_version == 1 else reply["invitations"]
            )
            for rank, rx, field_ in heuristics:
                if any(
                    re.match(string=inv, pattern=rx, flags=re.IGNORECASE)
                    for inv in invitations
                ):
                    if field_.startswith("="):
                        ranked_results.append((rank, field_[1:]))
                        break
                    elif field_ in reply["content"]:
                        ranked_results.append(
                            (rank, self.get_content_field(reply, field_))
                        )
                        break

        if ranked_results:
            ranked_results.sort()
            decisions = {
                decision
                for rank, decision in ranked_results
                if rank == ranked_results[0][0]
            }
            if len(decisions) == 1:
                decision = decisions.pop()
                return self.refine_decision(decision) or decision

        if from_venue := self.refine_decision(self.get_content_field(note, "venue", "")):
            return from_venue

        if from_vid := self.refine_decision(self.get_venue_id(note)):
            return from_vid

        if note.pdate:
            return "published"

        btx = note.content.get("_bibtex", "")
        if btx.startswith("@inproceedings") and note.id in btx:
            return "accepted"

        # welp. whatever.
        return None

    @staticmethod
    def _map_venue_type(venueid):
        for v_type in VenueType:
            if v_type in venueid.lower():
                return v_type
        else:
            return VenueType.unknown

    async def _query(self, params, total=0, limit=1000000):
        next_offset = 0
        while total < limit:
            params["offset"] = next_offset
            notes = self.client.get_notes(**params, details="replies")
            for note in notes:
                vid = self.get_venue_id(note)
                if not vid:
                    continue
                if "authors" not in note.content:
                    continue

                authors = []
                note_authors = self.get_content_field(note, "authors", [])
                note_authorids = self.get_content_field(note, "authorids", [])

                if len(note_authors) == len(note_authorids) and all(
                    (aid is None or aid.startswith("~") for aid in note_authorids)
                ):
                    authors_ids = note_authorids
                else:
                    authors_ids = (None for _ in range(len(note_authors)))
                for name, author_id in zip(note_authors, authors_ids):
                    _links = []
                    if author_id:
                        _links.append(
                            Link(type="openreview", link=author_id or f"/{name}")
                        )
                    authors.append(
                        PaperAuthor(
                            display_name=name,
                            affiliations=[],
                            author=Author(
                                name=name,
                                aliases=[],
                                links=_links,
                            ),
                        )
                    )
                _links = [Link(type="openreview", link=note.id)]
                if "code" in note.content:
                    Link(type="git", link=self.get_content_field(note, "code"))

                venue = self.get_content_field(note, "venue") or get_invitation(note)
                venue_data = parse_openreview_venue(venue)
                decision = self.figure_out_the_fking_decision(note) or "unknown"

                if "status" not in venue_data and note.pdate:
                    venue_data["status"] = "published"

                tstamp = note.pdate or note.odate or note.tcdate or note.tmdate
                the_date = date.fromtimestamp(tstamp // 1000)
                precision = DatePrecision.day
                if "year" in venue_data:
                    # Make sure that the year is correct
                    year = int(venue_data["year"])
                    if the_date.year != year:
                        the_date = date(year, 1, 1)
                        precision = DatePrecision.year
                    venue_data["venue"] += f" {year}"

                yield Paper(
                    key=f"openreview:{note.id}",
                    version=datetime.now(),
                    title=self.get_content_field(note, "title"),
                    abstract=self.get_content_field(note, "abstract"),
                    authors=authors,
                    releases=[
                        Release(
                            venue=Venue(
                                type=type(self)._map_venue_type(vid),
                                name=vid,
                                series=venue_to_series(vid),
                                volume=venue_data["venue"],
                                date=the_date,
                                date_precision=precision,
                                links=[
                                    Link(
                                        type="openreview-venue",
                                        link=vid,
                                    )
                                ],
                                aliases=[],
                            ),
                            status=decision,
                            pages=None,
                        )
                    ],
                    topics=[
                        Topic(name=kw)
                        for kw in self.get_content_field(note, "keywords", [])
                    ],
                    links=_links,
                    info={"discovered_by": {"openreview": note.id}},
                )
            next_offset += len(notes)
            if not notes or "id" in params:
                break
            total += next_offset

    async def _query_papers_from_venues(
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

            async for paper in self._query(params, total, limit):
                total += 1
                yield paper

    def _query_authors(self, author_or_email: str, /):
        # This endpoint requires an access token:
        # E           openreview.openreview.OpenReviewException: {'name': 'ForbiddenError', 'message': 'This action is forbidden. You must be logged in to access this resource. (2026-02-17-8058870)', 'status': 403, 'details': {'path': '/profiles/search?term=Yoshua+Bengio&es=false', 'user': 'guest_1771368244277', 'reqId': '2026-02-17-8058870'}}
        # https://api2.openreview.net/profiles/search
        for profile in self.client.search_profiles(term=author_or_email):
            yield profile.id

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

    def _venues_from_wildcard(self, pattern):
        if isinstance(pattern, list):
            return reduce(list.__add__, [self._venues_from_wildcard(p) for p in pattern])
        elif "*" not in pattern:
            return [pattern]
        else:
            members = self.client.get_group(id="venues").members
            return [
                member
                for member in members
                if fnmatch(pat=pattern.lower(), name=member.lower())
            ]

    async def query(
        self,
        # Venue of publication
        venue: str = None,
        # OpenReview ID of the paper
        paper_id: str = None,
        # Name of the author
        author: str = None,
        # OpenReview ID of the author
        author_id: str = None,
        # Title of the paper
        title: str = None,
        # Block size for fetching results
        block_size: int = 100,
        # Maximum number of results to return
        limit: int = 10000,
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query OpenReview"""
        if focuses:
            if limit is not None:
                print(
                    "The 'limit' parameter is ignored when 'focuses' are provided.",
                    file=sys.stderr,
                )

            for focus in focuses.focuses:
                match focus:
                    case Focus(drive_discovery=False):
                        continue
                    case Focus(type="author", name=name, score=score):
                        async for paper in self.query(
                            venue=venue,
                            author=name,
                            title=title,
                            block_size=block_size,
                        ):
                            paper.score = score
                            yield paper
                    case Focus(type="author_openreview", name=aid, score=score):
                        async for paper in self.query(
                            venue=venue,
                            author_id=aid,
                            title=title,
                            block_size=block_size,
                        ):
                            paper.score = score
                            yield paper
            return

        if not venue:
            venue = [None]
        else:
            venue = [venue]

        if author and venue == [None]:
            # OpenReview API does not support searching by author
            # name without a venue, so first search for the possible author IDs
            for author_id in self._query_authors(author):
                async for paper in self.query(
                    venue=None,
                    author_id=author_id,
                    title=title,
                    block_size=block_size,
                    limit=limit,
                ):
                    yield paper
            return

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
        if title:
            params = {
                **params,
                "content": {**params["content"], "title": title},
            }

        async for paper in self._query_papers_from_venues(params, venue, 0, limit):
            yield paper

    def login(self, username: str, password: str):
        if self.client.token or self.token:
            return self.client.token or self.token
        return OpenReview(
            api_version=self.api_version, username=username, password=password
        ).client.token


@dataclass
class OpenReviewDispatch(Discoverer):
    api_versions: list = dc_field(default_factory=lambda: [2, 1])
    token: Secret[str] = field(default_factory=lambda: openreview_api_key)

    async def query(
        self,
        # Venue of publication
        venue: str = None,
        # OpenReview ID of the paper
        paper_id: str = None,
        # Name of the author
        author: str = None,
        # OpenReview ID of the author
        author_id: str = None,
        # Title of the paper
        title: str = None,
        # Block size for fetching results
        block_size: int = 100,
        # Maximum number of results to return
        limit: int = 100000,
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query OpenReview"""
        for api_version in self.api_versions:
            o = OpenReview(api_version=api_version, token=self.token)
            q = o.query(
                venue=venue,
                paper_id=paper_id,
                author=author,
                author_id=author_id,
                title=title,
                block_size=block_size,
                limit=limit,
                focuses=focuses,
            )

            has_papers = False

            exception = None
            try:
                async for paper in q:
                    has_papers = True
                    yield paper

            except openreview.OpenReviewException as e:
                # Try the next API version while holding the exception
                exception = e
                continue

            if has_papers:
                break

        else:
            if exception is not None:
                raise exception

    async def login(self, username: str, password: str):
        for api_version in self.api_versions:
            try:
                return OpenReview(api_version=api_version).login(username, password)
            except openreview.OpenReviewException:
                continue


openreview_api_key: Secret[str] | None = gifnoc.define(
    "paperoni.discovery.openreview.api_key", Secret[str] | None, defaults=None
)
