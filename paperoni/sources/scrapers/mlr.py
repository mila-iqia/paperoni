import time
from datetime import datetime
from traceback import print_exc

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

from ...config import papconf
from ...utils import asciiify
from ..acquire import readpage
from .base import BaseScraper


def parse_paper(entry):
    if not entry.get("title", None) or not entry.get("author", None):
        return None
    p = Paper(
        title=entry["title"],
        abstract=entry.get("abstract", None),
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
                    date=datetime(*map(int, entry["issued"]["date-parts"])),
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
    def get_volume(self, volume, cache=False):
        print(f"Fetching PMLR {volume}")
        try:
            return readpage(
                f"https://proceedings.mlr.press/{volume}/assets/bib/citeproc.yaml",
                format="yaml",
                cache_into=cache
                and papconf.paths.cache
                and papconf.paths.cache / "mlr" / f"{volume}",
            )
        except Exception:
            print_exc()
            return []

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
            results = self.get_volume(vol, cache)
            for entry in results:
                paper = parse_paper(entry)
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
            "https://proceedings.mlr.press",
            format="html",
        )
        volumes = [
            lnk.attrs["href"] for lnk in main.select(".proceedings-list a")
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
            scraper="mlr",
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
    "mlr": MLRScraper,
}
