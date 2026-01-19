import traceback
from datetime import date, datetime
from traceback import print_exc

from outsight import send

from ..config import config
from ..model.classes import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
    Release,
    Venue,
    VenueType,
)
from ..model.focus import Focuses
from ..utils import asciiify
from .base import Discoverer


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
                    date=date(*map(int, entry["issued"]["date-parts"])),
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
    pmlr_key = f"v{entry['volume']}:{entry['id']}"
    paper_key = f"pmlr:{pmlr_key}"

    return PaperInfo(
        key=paper_key,
        acquired=datetime.now(),
        paper=p,
        info={"discovered_by": {"pmlr": pmlr_key}},
    )


class PMLR(Discoverer):
    async def query(
        self,
        # Volume to query
        # [alias: -v]
        volume: str = None,
        # Name to query
        # [alias: -n]
        name: str = None,
        # Whether to cache the download
        cache: bool = True,
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query Proceedings of Machine Learning Research."""
        name = name and asciiify(name).lower()
        if volume is None:
            for v in await self.list_volumes():
                async for paper in self.query(v, name, cache, focuses):
                    yield paper
            return
        async for paper_info in self.get_volume(volume, cache):
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

    async def get_volume(self, volume, cache=False):
        send(event=f"Fetching PMLR {volume}")
        try:
            papers = await config.fetch.read(
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

    async def extract_volumes(self, index, selector, map=None, filter=None):
        main = await config.fetch.read(index, format="html")
        urls = [lnk.attrs["href"] for lnk in main.select(selector)]
        return [map(url) if map else url for url in urls if filter is None or filter(url)]

    async def list_volumes(self):
        return await self.extract_volumes(
            index="https://proceedings.mlr.press",
            selector=".proceedings-list a",
        )
