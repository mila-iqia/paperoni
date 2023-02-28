from datetime import datetime

from coleo import Option, tooled

from paperoni.model import (
    Author,
    DatePrecision,
    Link,
    Meta,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)
from paperoni.sources.acquire import readpage

from ..acquire import readpage
from .base import BaseScraper


def parse_paper(entry):
    p = Paper(
        title=entry["title"],
        abstract=entry["abstract"],
        authors=[
            PaperAuthor(
                author=Author(
                    name=f"{author['given']} {author['family']}",
                    roles=[],
                    aliases=[],
                    links=[],
                ),
                affiliations=[],
            )
            for author in entry["author"]
        ],
        releases=[
            Release(
                venue=Venue(
                    name=entry["container-title"],
                    date=datetime(*entry["issued"]["date-parts"]),
                    date_precision=DatePrecision.day,
                    type=VenueType.unknown,
                    series=entry["container-title"],
                    aliases=[],
                    links=[],
                    peer_reviewed=True,
                    publisher=entry["publisher"],
                    quality=(1.0,),
                    volume=str(entry["volume"]),
                ),
                status="published",
                pages=entry["page"],
            )
        ],
        topics=[],
        links=[
            Link(type="mlr", link=f"{entry['volume']}/{entry['id']}"),
            Link(type="pdf", link=entry["PDF"]),
        ],
    )
    return p


class MLRScraper(BaseScraper):
    @tooled
    def query(
        self,
        # Volume to query
        # [alias: -v]
        volume: Option = None,
    ):
        results = readpage(
            f"https://proceedings.mlr.press/v{volume}/assets/bib/citeproc.yaml",
            format="yaml",
        )
        for entry in results:
            yield parse_paper(entry)

    @tooled
    def acquire(self):
        # Volume to query
        # [alias: -v]
        volume: Option = (None,)

        yield Meta(
            scraper="mlr",
            date=datetime.now(),
        )
        yield from self.query(volume)

    @tooled
    def prepare(self):
        pass


__scrapers__ = {
    "mlr": MLRScraper,
}
