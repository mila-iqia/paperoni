import time
from datetime import datetime
from traceback import print_exc

import bibtexparser
from coleo import Option, tooled
from requests import HTTPError

from ...config import papconf
from ...model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
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


class NeurIPSScraper(BaseScraper):
    urlbase = "https://proceedings.neurips.cc"

    def get_paper_json(self, volume, hsh, html, conference_title):
        pdf_path = (
            html.replace("Abstract", "Paper")
            .replace(".html", ".pdf")
            .replace("/hash/", "/file/")
        )
        metalink = f"{self.urlbase}/paper_files/paper/{volume}/file/{hsh}-Metadata.json"
        entry = readpage(metalink, format="json")
        return Paper(
            title=entry["title"],
            abstract=entry.get("abstract", ""),
            authors=[
                PaperAuthor(
                    author=Author(
                        name=f'{author["given_name"]} {author["family_name"]}',
                        roles=[],
                        aliases=[],
                        links=[],
                    ),
                    affiliations=[
                        Institution(
                            name=author["institution"],
                            category=InstitutionCategory.unknown,
                            aliases=[],
                        )
                    ]
                    if author["institution"]
                    else [],
                )
                for author in entry["authors"]
            ],
            releases=[
                Release(
                    venue=Venue(
                        name=conference_title,
                        date=datetime(int(volume), 1, 1),
                        date_precision=DatePrecision.year,
                        type=VenueType.unknown,
                        series=entry["book"],
                        aliases=[],
                        links=[],
                        peer_reviewed=True,
                        publisher=entry.get("publisher", ""),
                        quality=(1.0,),
                        volume=str(entry.get("volume", "")),
                    ),
                    status="published",
                    pages=f'{entry["page_first"]}--{entry["page_last"]}',
                )
            ],
            topics=[],
            links=[
                Link(type="html.official", link=f"{self.urlbase}/{html}"),
                Link(type="pdf.official", link=f"{self.urlbase}/{pdf_path}"),
            ],
        )

    def get_paper_bibtex(self, volume, hsh, html, conference_title):
        biblink = (
            f"{self.urlbase}/paper_files/paper/{volume}/file/{hsh}-Bibtex.bib"
        )
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
                        # name=f'{entry["volume"]}th Conference on {entry["booktitle"]}',
                        name=conference_title,
                        date=datetime(int(volume), 1, 1),
                        date_precision=DatePrecision.year,
                        type=VenueType.unknown,
                        series=entry["booktitle"],
                        aliases=[],
                        links=[],
                        peer_reviewed=True,
                        publisher=entry["publisher"],
                        quality=(1.0,),
                        volume=str(entry["volume"]),
                    ),
                    status="published",
                    pages=entry["pages"],
                )
            ],
            topics=[],
            links=[
                Link(type="html.official", link=f"{self.urlbase}/{html}"),
                Link(type="pdf.official", link=entry["url"]),
            ],
        )

    def get_paper(self, volume, hsh, html, conference_title):
        try:
            return self.get_paper_json(volume, hsh, html, conference_title)
        except HTTPError:
            return self.get_paper_bibtex(volume, hsh, html, conference_title)

    def get_volume(self, volume, names, cache=False):
        print(f"Fetching NeurIPS {volume}")
        try:
            index = readpage(
                f"{self.urlbase}/paper_files/paper/{volume}",
                format="html",
                cache_into=cache
                and papconf.paths.cache
                and papconf.paths.cache / "neurips" / f"{volume}",
            )
        except Exception:
            print_exc()
            return

        conference_title = index.select_one("h4").text
        assert "Neural Information Processing Systems" in conference_title

        for entry in index.select("li"):
            link = entry.select_one("a")["href"]
            if f"paper/{volume}/hash" in link:
                hsh = link.split("/")[-1].split("-")[0]
                if names:
                    authors = asciiify(entry.select_one("i").text).lower()
                    if not any(name in authors for name in names):
                        continue
                paper = self.get_paper(volume, hsh, link, conference_title)
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
            self.urlbase,
            format="html",
        )
        volumes = [
            lnk.attrs["href"].split("/")[-1]
            for lnk in main.select(".col-sm ul li a")
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
            scraper="neurips",
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
    "neurips": NeurIPSScraper,
}
