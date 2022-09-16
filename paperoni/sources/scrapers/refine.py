import http.client
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup
from coleo import Option, tooled
from sqlalchemy import select

from ...config import load_config
from ...db import schema as sch
from ...model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    UniqueAuthor,
    UniqueInstitution,
    Venue,
    VenueType,
)
from ...tools import extract_date, keyword_decorator
from .base import BaseScraper
from .pdftools import find_fulltext_affiliations, pdf_to_text

refiners = defaultdict(list)


def readpage(url, format=None):
    domain = url.split("/")[2]
    conn = http.client.HTTPSConnection(domain)
    conn.request("GET", url)
    resp = conn.getresponse()
    if resp.status == 301:
        loc = resp.info().get_all("Location")[0]
        return readpage(loc, format=format)
    else:
        content = resp.read()
        resp.close()
        match format:
            case "json":
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return None
            case "xml":
                return BeautifulSoup(content, features="xml")
            case "html":
                return BeautifulSoup(content, features="html")
            case _:
                return content


@keyword_decorator
def refiner(fn, *, type, priority):
    refiners[type].append((priority, fn))
    return fn


def _paper_from_jats(soup, links):
    date1 = soup.select_one('pub-date[date-type="pub"] string-date')
    if date1:
        date = extract_date(date1.text)
    else:
        date2 = soup.select_one('pub-date[pub-type="epub"]')
        if date2:
            y = date2.find("year")
            m = date2.find("month")
            d = date2.find("day")
            date = {
                "date": datetime(
                    int(y.text),
                    int((m and m.text) or 1),
                    int((d and d.text) or 1),
                ),
                "date_precision": (
                    DatePrecision.day
                    if d
                    else DatePrecision.month
                    if m
                    else DatePrecision.year
                ),
            }

    return Paper(
        title=soup.find("article-title").text,
        authors=[
            PaperAuthor(
                author=Author(
                    name=" ".join(
                        [
                            x.text
                            for x in [
                                *author.find_all("given-names"),
                                author.find("surname"),
                            ]
                        ]
                    ),
                    aliases=[],
                    links=[],
                    roles=[],
                    quality=(0,),
                ),
                affiliations=[
                    Institution(
                        name=soup.select_one(
                            f'aff#{aff.attrs["rid"]} institution, aff#{aff.attrs["rid"]}'
                        ).text,
                        category=InstitutionCategory.unknown,
                        aliases=[],
                    )
                    for aff in author.select('xref[ref-type="aff"]')
                ],
            )
            for author in soup.select('contrib[contrib-type="author"]')
        ],
        abstract="",
        links=links,
        releases=[
            Release(
                venue=Venue(
                    name=(
                        jname := soup.select_one(
                            "journal-meta journal-title"
                        ).text
                    ),
                    series=jname,
                    type=VenueType.journal,
                    **date,
                    publisher=soup.select_one(
                        "journal-meta publisher-name"
                    ).text,
                    links=[],
                    aliases=[],
                ),
                status="published",
                pages=None,
            )
        ],
        topics=[Topic(name=kwd.text) for kwd in soup.select("kwd-group kwd")],
        quality=(0,),
    )


@refiner(type="doi", priority=100)
def refine_doi_with_crossref(db, paper, link):
    doi = link.link
    data = readpage(f"https://api.crossref.org/v1/works/{doi}", format="json")

    if data["status"] != "ok":
        return None
    data = SimpleNamespace(**data["message"])

    if not any(auth.get("affiliation", None) for auth in data.author):
        return None

    return Paper(
        title=data.title[0],
        authors=[
            PaperAuthor(
                author=Author(
                    name=f"{author['given']} {author['family']}",
                    roles=[],
                    aliases=[],
                    links=[],
                ),
                affiliations=[
                    Institution(
                        name=aff["name"],
                        category=InstitutionCategory.unknown,
                        aliases=[],
                    )
                    for aff in author["affiliation"]
                ],
            )
            for author in data.author
        ],
        abstract="",
        links=[Link(type="doi", link=doi)],
        topics=[],
        releases=[],
        quality=(0,),
    )


@refiner(type="doi", priority=90)
def refine_doi_with_biorxiv(db, paper, link):
    doi = link.link
    if not doi.startswith("10.1101/"):
        return None

    data = readpage(
        f"https://api.biorxiv.org/details/biorxiv/{doi}", format="json"
    )

    if {"status": "ok"} not in data["messages"] or not data["collection"]:
        return None

    jats = data["collection"][0]["jatsxml"]

    return _paper_from_jats(
        readpage(jats, format="xml"),
        links=[Link(type="doi", link=doi)],
    )


@refiner(type="pmc", priority=110)
def refine(db, paper, link):
    pmc_id = link.link
    soup = readpage(
        f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm",
        format="xml",
    )
    return _paper_from_jats(
        soup,
        links=[Link(type="pmc", link=pmc_id)],
    )


def _pdf_refiner(db, paper, link, pth, url):

    fulltext = pdf_to_text(cache_base=pth, url=url)

    institutions = {}
    for (inst,) in db.session.execute(select(sch.Institution)):
        institutions.update({alias: inst for alias in inst.aliases})

    author_affiliations = find_fulltext_affiliations(
        paper, fulltext, institutions
    )

    if not author_affiliations:
        return None

    return Paper(
        title=paper.title,
        abstract="",
        authors=[
            PaperAuthor(
                author=UniqueAuthor(
                    author_id=author.author_id,
                    name=author.name,
                    roles=[],
                    aliases=[],
                    links=[],
                    quality=author.quality,
                ),
                affiliations=[
                    UniqueInstitution(
                        institution_id=aff.institution_id,
                        name=aff.name,
                        category=aff.category,
                        aliases=[],
                    )
                    for aff in affiliations
                ],
            )
            for author, affiliations in author_affiliations.items()
        ],
        links=[Link(type=link.type, link=link.link)],
        releases=[],
        topics=[],
        quality=(0,),
    )


@refiner(type="arxiv", priority=5)
def refine(db, paper, link):
    arxiv_id = link.link
    config = load_config()

    return _pdf_refiner(
        db=db,
        paper=paper,
        link=link,
        pth=Path(f"{config.cache_root}/arxiv/{arxiv_id}.pdf"),
        url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
    )


@refiner(type="openreview", priority=5)
def refine(db, paper, link):
    openreview_id = link.link
    config = load_config()

    return _pdf_refiner(
        db=db,
        paper=paper,
        link=link,
        pth=Path(f"{config.cache_root}/openreview/{openreview_id}.pdf"),
        url=f"https://openreview.net/pdf?id={openreview_id}",
    )


class Refiner(BaseScraper):
    @tooled
    def query(
        self,
        # [positional]
        # Link to query
        link: Option = None,
    ):
        type, link = link.split(":", 1)
        pq = (
            select(sch.Paper)
            .join(sch.PaperLink)
            .filter(sch.PaperLink.type == type, sch.PaperLink.link == link)
        )
        [[paper], *_] = self.db.session.execute(pq)

        _refiners = []
        for link in paper.links:
            _refiners.extend(
                [(p, link, r) for (p, r) in refiners.get(link.type, [])]
            )

        _refiners.sort(reverse=True, key=lambda data: data[0])

        for _, link, refiner in _refiners:
            if result := refiner(self.db, paper, link):
                yield result
                return

    @tooled
    def acquire(self):
        pass

    @tooled
    def prepare(self):
        pass


__scrapers__ = {"refine": Refiner}
