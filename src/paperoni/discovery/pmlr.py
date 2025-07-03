import traceback
from datetime import datetime
from traceback import print_exc

from ..acquire import readpage
from ..config import config
from ..model.classes import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)
from ..utils import asciiify
from .base import Discoverer, PaperInfo


def parse_paper(entry):
    if not entry.get("title", None) or not entry.get("author", None):
        return None
    p = Paper(
        title=entry["title"],
        abstract=entry.get("abstract", None),
        authors=[
            PaperAuthor(
                display_name=(name := f"{author['given']} {author['family']}"),
                author=Author(
                    name=name,
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

    # Create unique key based on volume and ID
    paper_key = f"pmlr:v{entry['volume']}:{entry['id']}"

    return PaperInfo(
        key=paper_key,
        acquired=datetime.now(),
        paper=p,
    )


class PMLR(Discoverer):
    def query(
        self,
        # Volume to query
        # [alias: -v]
        volume: str = None,
        # Name to query
        # [alias: -n]
        name: str = None,
        # Whether to cache the download
        cache: bool = True,
    ):
        name = name and asciiify(name).lower()
        results = self.get_volume(volume, cache)
        for paper_info in results:
            try:
                if (
                    paper_info
                    and paper_info.paper
                    and (
                        name is None
                        or any(
                            asciiify(auth.author.name).lower() == name
                            for auth in paper_info.paper.authors
                        )
                    )
                ):
                    yield paper_info
            except Exception as exc:
                traceback.print_exception(exc)

    def get_volume(self, volume, cache=False):
        print(f"Fetching PMLR {volume}")
        try:
            papers = readpage(
                f"https://proceedings.mlr.press/{volume}/assets/bib/citeproc.yaml",
                format="yaml",
                cache_into=cache
                and config.cache_path
                and config.cache_path / "pmlr" / f"{volume}.yaml",
            )
            for paper in papers:
                yield parse_paper(paper)
        except Exception:
            print_exc()

    def extract_volumes(self, index, selector, map=None, filter=None):
        main = readpage(index, format="html")
        urls = [lnk.attrs["href"] for lnk in main.select(selector)]
        return [map(url) if map else url for url in urls if filter is None or filter(url)]

    def list_volumes(self):
        return self.extract_volumes(
            index="https://proceedings.mlr.press",
            selector=".proceedings-list a",
        )
