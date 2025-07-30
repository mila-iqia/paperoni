import math
import re
from datetime import datetime
from enum import Enum

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


class MiniConf(Discoverer):
    def convert_paper(self, data, conference=None, venue_date=None):
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
            date_precision=DatePrecision.day,
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
        if url := expand_base(data.get("paper_url")):
            links.add(Link(type="abstract", link=url))
        if url := expand_base(data.get("paper_pdf_url")):
            links.add(Link(type="pdf", link=url))
        if url := expand_base(data.get("virtualsite_url")):
            links.add(Link(type="abstract", link=url))

        # Add eventmedia links
        for media in data.get("eventmedia", []):
            if media.get("uri") and media.get("visible", True):
                media_type = media.get("name", "").lower().replace(" ", "_")
                uri = media["uri"]
                if uri.startswith("https://openreview.net/forum?id="):
                    uri = uri.split("=")[-1]
                else:
                    uri = expand_base(uri)
                links.add(Link(type=media_type, link=uri))

        links = sorted(
            links, key=lambda x: ({"pdf": 0}.get(x.type, math.inf), x.type, x.link)
        )

        # Create and return Paper object
        return PaperInfo(
            key=f"miniconf:{conference}:{data['uid']}",
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
        )

    def query(
        self,
        # Conference name (e.g. "neurips", "icml", "iclr", "mlsys", "aistats", "cvpr")
        conference: str,
        # Year of the conference
        year: int,
        # Filter on an affiliation
        affiliation: str = None,
        # Filter on an author
        author: str = None,
        # Maximum number of papers to yield
        limit: int = None,
        # Whether to cache the download
        cache: bool = True,
        # Whether to raise an error if a paper cannot be converted
        error_policy: ErrorPolicy = ErrorPolicy.LOG,
    ):
        """Query conference papers as JSON"""
        # Get the base URL for the conference, defaulting to conference.cc if not found
        base_url = conference_urls[conference.lower()]
        base_url = f"https://{base_url}"

        url = f"{base_url}/static/virtual/data/{conference}-{year}-orals-posters.json"
        data = config.fetch.read(
            url,
            format="json",
            cache_into=cache
            and config.cache_path
            and config.cache_path / "miniconf" / f"{conference}-{year}.json",
        )

        uid_groups = {}

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
            conference_date = datetime(year, 1, 1)

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
                    paper_data, conference=conference, venue_date=conference_date
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


# https://{{ conference_website }}/static/virtual/data/{{ conference_name }}-{{ year }}-orals-posters.json
# This goes for neurips, icml, iclr, mlsys, aistats and cvpr (edited)
