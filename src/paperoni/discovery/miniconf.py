import math
import re
from datetime import date, datetime, timedelta
from enum import Enum

import requests

from ..config import config
from ..model.classes import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
    Release,
    Topic,
    Venue,
    VenueType,
)
from ..model.focus import Focuses
from .base import Discoverer

conference_urls = {
    "neurips": "neurips.cc",
    "icml": "icml.cc",
    "iclr": "iclr.cc",
    "mlsys": "mlsys.org",
    "aistats": "virtual.aistats.org",
    "cvpr": "cvpr.thecvf.com",
}


class ErrorPolicy(Enum):
    LOG = "log"
    RAISE = "raise"


pdf_mappings = [
    {
        "pattern": r"https://proceedings\.neurips\.cc//?paper_files/paper/(?P<year>\d{4})/hash/(?P<hash>[a-f0-9]{32})-Abstract(?P<suffix>.*)\.html",
        "pdf": "https://proceedings.neurips.cc/paper_files/paper/{year}/file/{hash}-Paper{suffix}.pdf",
    },
    {
        "pattern": r"https://openaccess.thecvf.com/content/CVPR(?P<year>\d{4})/html/(?P<lnk>.*).html",
        "pdf": "https://openaccess.thecvf.com/content/CVPR{year}/papers/{lnk}.pdf",
    },
]


def map_pdf_url(url):
    for mapping in pdf_mappings:
        pattern = mapping["pattern"]
        m = re.match(pattern, url)
        if m:
            pdf_template = mapping["pdf"]
            return pdf_template.format(**m.groupdict())
    return None


class MiniConf(Discoverer):
    def convert_paper(
        self, data, conference=None, venue_date=None, date_precision=DatePrecision.day
    ):
        """Convert JSON data from conference API to Paper object"""
        # Extract basic paper information
        title = data.get("name", "")
        abstract = data.get("abstract", "")

        # Convert authors
        authors = []
        for author_data in data.get("authors", []):
            # Create Author object
            author = Author(
                name=author_data.get("fullname", ""),
                aliases=[],
                links=[
                    (
                        Link(type="profile", link=author_data["url"])
                        if author_data.get("url")
                        else None
                    )
                ],
            )
            author.links = [link for link in author.links if link is not None]

            # Create institution if available
            affiliations = []
            if author_data.get("institution"):
                institution = Institution(
                    name=author_data["institution"],
                    category=InstitutionCategory.unknown,
                    aliases=[],
                )
                affiliations.append(institution)

            # Create PaperAuthor
            paper_author = PaperAuthor(
                author=author,
                display_name=author_data.get("fullname", ""),
                affiliations=affiliations,
            )
            authors.append(paper_author)

        # Create venue from conference information
        conference_name = conference.upper() if conference else "Unknown Conference"

        venue = Venue(
            type=VenueType.conference,
            name=conference_name,
            series=conference_name,
            date=venue_date,
            date_precision=date_precision,
            aliases=[],
            links=[],
            open=True,
            peer_reviewed=True,
        )

        status = data.get("decision", None)
        if status is None:
            if data.get("poster_number", None):
                status = "Accept (poster)"
            else:
                status = "Accept"

        # Create release
        release = Release(venue=venue, status=status, pages=None)

        # Convert topics
        topics = []
        if data.get("topic"):
            topics.append(Topic(name=data["topic"]))

        # Convert keywords to topics as well
        for keyword in data.get("keywords", []):
            if keyword:  # Only add non-empty keywords
                topics.append(Topic(name=keyword))

        def expand_base(uri):
            """Expand relative URIs to absolute URLs using the base URL."""
            if not uri:
                return None
            elif uri.startswith("/"):
                return f"{data['base_url']}{uri}"
            elif uri.startswith("http"):
                return uri
            else:
                return f"{data['base_url']}/{uri}"

        # Extract links
        links = set()

        def process_uri(media_type, uri):
            if uri.startswith("https://openreview.net/forum?id="):
                uri = uri.split("=")[-1]
                media_type = "openreview"
            elif m := re.match(
                r"^https?://proceedings\.mlr\.press/v(\d+)/([^\./]+)", uri
            ):
                vol, tag = m.groups()
                uri = f"{vol}/{tag}"
                media_type = "mlr"
            else:
                uri = expand_base(uri)
            links.add(Link(type=media_type, link=uri))

        if url := expand_base(data.get("paper_url")):
            process_uri("abstract", url)
        if url := expand_base(data.get("paper_pdf_url")):
            process_uri("pdf", url)
        if url := expand_base(data.get("virtualsite_url")):
            process_uri("abstract", url)
        links.add(Link(type="uid", link=f"{conference}/{venue_date}/{data['uid']}"))

        # Add eventmedia links
        for media in data.get("eventmedia", []):
            if media.get("uri") and media.get("visible", True):
                media_type = media.get("name", "").lower().replace(" ", "_")
                uri = media["uri"]
                process_uri(media_type, uri)

        for lnk in list(links):
            if pdf_url := map_pdf_url(lnk.link):
                links.add(Link(type="pdf", link=pdf_url))

        # Remove "pdf" links that aren't actually pdfs
        links = [
            lnk
            for lnk in list(links)
            if "pdf" not in lnk.type or lnk.link.endswith(".pdf")
        ]

        links = sorted(
            links, key=lambda x: ({"pdf": 0}.get(x.type, math.inf), x.type, x.link)
        )
        mid = f"{conference}:{data['uid']}"

        # Create and return Paper object
        return PaperInfo(
            key=f"miniconf:{mid}",
            acquired=datetime.now(),
            paper=Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                releases=[release],
                topics=topics,
                links=list(links),
                flags=[],
            ),
            info={"discovered_by": {"miniconf": mid}},
        )

    async def query(
        self,
        # Conference name (e.g. "neurips", "icml", "iclr", "mlsys", "aistats", "cvpr")
        conference: str,
        # Year of the conference
        year: int = None,
        # Filter on an affiliation
        affiliation: str = None,
        # Filter on an author
        author: str = None,
        # Maximum number of papers to yield
        limit: int = None,
        # Whether to cache the download
        cache: bool = True,
        # Cache expiry
        cache_expiry: timedelta = None,
        # Whether to raise an error if a paper cannot be converted
        error_policy: ErrorPolicy = ErrorPolicy.LOG,
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query conference papers as JSON"""
        if year is None:
            current = datetime.now().year
            consecutive_failures = 0
            while consecutive_failures <= 2:
                try:
                    async for paper in self.query(
                        conference,
                        year=current,
                        affiliation=affiliation,
                        author=author,
                        limit=limit,
                        cache=cache,
                        error_policy=error_policy,
                    ):
                        yield paper
                    consecutive_failures = 0
                except requests.HTTPError:
                    consecutive_failures += 1
                current -= 1
            return

        # Get the base URL for the conference, defaulting to conference.cc if not found
        base_url = conference_urls[conference.lower()]
        base_url = f"https://{base_url}"

        url = f"{base_url}/static/virtual/data/{conference}-{year}-orals-posters.json"
        cache_path = (
            cache
            and config.cache_path
            and config.cache_path / "miniconf" / f"{conference}-{year}.json"
        )
        data = await config.fetch.aread(
            url, format="json", cache_into=cache_path, cache_expiry=cache_expiry
        )

        uid_groups = {}

        if not data.get("results", None) and cache_path and cache_path.exists():
            cache_path.unlink()

        for paper_data in data["results"]:
            uid = paper_data.get("uid")
            if uid:
                if uid not in uid_groups:
                    uid_groups[uid] = []
                uid_groups[uid].append(paper_data)

        for uid, papers in uid_groups.items():
            # Merge eventmedias from all papers with the same UID into the first paper
            first_paper = papers[0]
            all_eventmedias = [media for paper in papers for media in paper["eventmedia"]]
            first_paper["eventmedia"] = all_eventmedias

        data["results"] = [papers[0] for papers in uid_groups.values()]

        # Find the minimum starttime across all papers to determine conference date
        conference_date = None
        date_precision = DatePrecision.day
        for paper_data in data["results"]:
            if paper_data.get("starttime"):
                try:
                    paper_starttime = datetime.fromisoformat(
                        paper_data["starttime"].replace("Z", "+00:00")
                    )
                    if conference_date is None or paper_starttime < conference_date:
                        conference_date = paper_starttime
                except (ValueError, TypeError):
                    # Skip papers with invalid starttime format
                    continue
        if conference_date:
            conference_date = conference_date.date()

        # If no valid starttime found, use a default date
        if conference_date is None:
            conference_date = date(year, 1, 1)
            date_precision = DatePrecision.year

        def matches(paper):
            if not affiliation and not author:
                return True
            if affiliation and any(
                re.search(rf"\b{re.escape(affiliation.lower())}\b", aff.name.lower())
                for author_info in paper.authors
                for aff in author_info.affiliations
            ):
                return True
            if author and any(
                re.search(
                    rf"\b{re.escape(author.lower())}\b", author_info.author.name.lower()
                )
                for author_info in paper.authors
            ):
                return True
            return False

        n = 0
        for paper_data in data["results"]:
            paper_data["base_url"] = base_url
            try:
                paper = self.convert_paper(
                    paper_data,
                    conference=conference,
                    venue_date=conference_date,
                    date_precision=date_precision,
                )
                if matches(paper.paper):
                    n += 1
                    yield paper
            except Exception as e:
                if error_policy == ErrorPolicy.RAISE:
                    raise
                # Log the error but continue processing other papers
                print(
                    f"Error converting paper '{paper_data.get('name', 'Unknown')}': {e}"
                )
                continue
            if limit and n >= limit:
                break
