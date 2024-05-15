import time
from datetime import datetime
from traceback import print_exc

import bibtexparser
from coleo import Option, tooled

from ...config import papconf
from ...model import (
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
from ...utils import asciiify
from ..acquire import readpage
from .base import BaseScraper


class JMRLScraper(BaseScraper):
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

    @tooled
    def query(
        self,
        # Volume(s) to query
        # [alias: -v]
        # [action: append]
        volume: Option = None,
        # Name(s) to query
        # [alias: --name]
        # [action: append]
        name: Option = None,
        # Whether to cache the download
        # [negate]
        cache: Option & bool = True,
    ):
        names = name and {asciiify(n).lower() for n in name}
        for i, vol in enumerate(volume):
            if i > 0:
                time.sleep(1)
            results = self.get_volume(vol, names, cache)
            for paper in results:
                if not paper:
                    continue
                if names is None or any(
                    asciiify(auth.author.name).lower() in names
                    for auth in paper.authors
                ):
                    yield paper

    @tooled
    def acquire(self):
        main = readpage(
            f"{self.urlbase}/papers",
            format="html",
        )
        volumes = [
            url
            for lnk in main.select("a")
            if (url := lnk.attrs["href"]).startswith("v")
        ]
        q = """
        SELECT DISTINCT alias from author
               JOIN author_alias as aa ON author.author_id = aa.author_id
               JOIN author_institution as ai ON ai.author_id = author.author_id
               JOIN institution as it ON it.institution_id = ai.institution_id
            WHERE it.name = "Mila";
        """
        names = [name for (name,) in self.db.session.execute(q)]

        yield Meta(
            scraper="jmlr",
            date=datetime.now(),
        )
        yield from self.query(
            volume=volumes,
            name=names,
        )

    @tooled
    def prepare(self):
        pass


__scrapers__ = {
    "jmlr": JMRLScraper,
}
