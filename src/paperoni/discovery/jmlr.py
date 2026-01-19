import logging
import re
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


class JMLR(Discoverer):
    urlbase = "https://jmlr.org"

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
        """Query Journal of Machine Learning Research."""
        if volume is None:
            for v in await self.list_volumes():
                async for paper in self.query(v, name, cache, focuses):
                    yield paper
            return
        name = name and asciiify(name).lower()
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
        send(event=f"Fetching JMLR {volume}")
        try:
            index = await config.fetch.read(
                f"{self.urlbase}/papers/{volume}",
                format="html",
                cache_into=cache
                and config.cache_path
                and config.cache_path / "jmlr" / f"{volume}.html",
            )
        except Exception:
            print_exc()
            return

        def absolutize(lnk):
            if lnk.startswith("/"):
                lnk = f"{self.urlbase}{lnk}"
            return lnk

        for entry in index.select("dl"):
            title = entry.select_one("dt").text.strip()
            author_names = entry.select_one("b").text.split(",")
            author_names = [name.strip() for name in author_names]
            lnks = {x.text: x.attrs["href"] for x in entry.select("a")}
            links = []
            uid = None
            if "pdf" in lnks:
                uid = absolutize(lnks["pdf"])
                links.append(Link(type="pdf.official", link=uid))
            if "bib" in lnks:
                uid = absolutize(lnks["bib"])
                links.append(Link(type="bibtex", link=uid))
            if "abs" in lnks:
                uid = absolutize(lnks["abs"])
                links.append(Link(type="abstract.official", link=uid))
            if uid:
                links.append(Link(type="uid", link=uid))

            # Extract page numbers and year from the text after authors (dd > b)
            text_after_authors = entry.select_one("dd > b").next_sibling
            if text_after_authors:
                text_after_authors = text_after_authors.strip()
                # Look for pattern like "; (2):1−86, 2024." after the authors
                page_year_match = re.search(
                    r";\s*\((\d+)\):(\d+)−(\d+),\s*(\d{4})", text_after_authors
                )
                if page_year_match:
                    # volume_num = page_year_match.group(1)
                    start_page = page_year_match.group(2)
                    end_page = page_year_match.group(3)
                    year = int(page_year_match.group(4))
                    pages = f"{start_page}-{end_page}"
                else:
                    logging.warning(
                        f"Could not extract year for paper '{title}' in volume {volume}"
                    )
                    continue
            else:
                logging.warning(
                    f"Could not extract year for paper '{title}' in volume {volume}"
                )
                continue

            paper = Paper(
                title=title,
                authors=[
                    PaperAuthor(
                        display_name=name,
                        author=Author(
                            name=name,
                            aliases=[],
                            links=[],
                        ),
                        affiliations=[],
                    )
                    for name in author_names
                ],
                releases=[
                    Release(
                        venue=Venue(
                            name="Journal of Machine Learning Research",
                            date=date(year, 1, 1),
                            date_precision=DatePrecision.year,
                            type=VenueType.journal,
                            series="JMLR",
                            aliases=[],
                            links=[],
                            peer_reviewed=True,
                            publisher="JMLR",
                        ),
                        status="published",
                        pages=pages,
                    )
                ],
                topics=[],
                links=links,
            )

            # Create unique key based on volume and title
            jmlr_key = f"{volume}:{title[:50].replace(' ', '_').lower()}"
            paper_key = f"jmlr:{jmlr_key}"

            yield PaperInfo(
                key=paper_key,
                acquired=datetime.now(),
                paper=paper,
                info={"discovered_by": {"jmlr": jmlr_key}},
            )

    async def extract_volumes(self, index, selector, map=None, filter=None):
        main = await config.fetch.read(index, format="html")
        urls = [lnk.attrs["href"] for lnk in main.select(selector)]
        return [map(url) if map else url for url in urls if filter is None or filter(url)]

    async def list_volumes(self):
        return await self.extract_volumes(
            index=f"{self.urlbase}/papers",
            selector="a",
            filter=lambda url: url.startswith("v"),
        )
