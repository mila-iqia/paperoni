from datetime import datetime
from traceback import print_exc

import bibtexparser

from ...config import papconf
from ...model import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)
from ...utils import asciiify
from ..acquire import readpage
from .base import ProceedingsScraper


class JMRLScraper(ProceedingsScraper):
    scraper_name = "jmlr"
    urlbase = "https://jmlr.org"

    def get_paper(self, links):
        biblink = f"{self.urlbase}{links['bib']}"
        raw_data = readpage(biblink)
        data = bibtexparser.parse_string(
            raw_data,
            append_middleware=[
                bibtexparser.middlewares.LatexDecodingMiddleware(),
                bibtexparser.middlewares.SeparateCoAuthors(),
                bibtexparser.middlewares.SplitNameParts(),
            ],
        )
        entry = {field.key: field.value for field in data.entries[0].fields}
        return Paper(
            title=entry["title"],
            abstract=entry.get("abstract", ""),
            authors=[
                PaperAuthor(
                    author=Author(
                        name=author.merge_first_name_first,
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
                        name=entry["journal"],
                        date=datetime(int(entry["year"]), 1, 1),
                        date_precision=DatePrecision.year,
                        type=VenueType.unknown,
                        series=entry["journal"],
                        aliases=[],
                        links=[],
                        peer_reviewed=True,
                        publisher="JMLR",
                        quality=(1.0,),
                        volume=str(entry["volume"]),
                    ),
                    status="published",
                    pages=entry["pages"],
                )
            ],
            topics=[],
            links=[
                Link(
                    type="html.official", link=f"{self.urlbase}{links['abs']}"
                ),
                Link(type="pdf.official", link=f"{self.urlbase}{links['pdf']}"),
            ],
        )

    def get_volume(self, volume, names, cache=False):
        print(f"Fetching JMLR {volume}")
        try:
            index = readpage(
                f"{self.urlbase}/papers/{volume}",
                format="html",
                cache_into=cache
                and papconf.paths.cache
                and papconf.paths.cache / "jmlr" / f"{volume}",
            )
        except Exception:
            print_exc()
            return

        for entry in index.select("dl"):
            links = {x.text: x.attrs["href"] for x in entry.select("a")}
            if "bib" not in links:
                continue
            if names:
                authors = asciiify(entry.select_one("b").text).lower()
                if not any(name in authors for name in names):
                    continue
            paper = self.get_paper(links)
            if paper:
                yield paper

    def list_volumes(self):
        return self.extract_volumes(
            index=f"{self.urlbase}/papers",
            selector="a",
            filter=lambda url: url.startswith("v"),
        )


__scrapers__ = {
    "jmlr": JMRLScraper,
}
