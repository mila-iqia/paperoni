import http.client
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup
from coleo import Option, tooled
from sqlalchemy import select

from paperoni.config import load_config, load_database
from paperoni.model import (
    Author,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Topic,
    Venue,
    VenueType,
)

from ...config import load_config, load_database
from ...db import schema as sch
from ...tools import extract_date, keyword_decorator
from .base import BaseScraper
from .pdftools import find_fulltext_affiliations, pdf_to_text

refiners = defaultdict(list)


@keyword_decorator
def refiner(fn, *, type, priority):
    refiners[type].append((priority, fn))
    return fn


@refiner(type="pmc", priority=10)
def refine(db, paper, link):
    pmc_id = link.link
    url = f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm"
    conn = http.client.HTTPSConnection("www.ncbi.nlm.nih.gov")
    conn.request("GET", url)
    txt = conn.getresponse().read()
    soup = BeautifulSoup(txt, features="xml")
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
                            f'aff#{aff.attrs["rid"]} institution'
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
        links=[Link(type="pmc", link=pmc_id)],
        releases=[
            Release(
                venue=Venue(
                    name=(jname := soup.find("journal-title").text),
                    series=jname,
                    type=VenueType.journal,
                    **extract_date(
                        soup.select_one(
                            'pub-date[date-type="pub"] string-date'
                        ).text
                    ),
                    publisher=soup.find("publisher-name").text,
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


def _pdf_refiner(db, paper, link, pth, url):

    fulltext = pdf_to_text(cache_base=pth, url=url)

    institutions = db.session.execute(
        "SELECT institution_id, alias FROM institution_alias"
    )
    institutions = {alias: iid for iid, alias in institutions}

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
                author=Author(
                    name=author.name,
                    roles=[],
                    aliases=[],
                    links=[],
                    quality=(0,),
                ),
                affiliations=[
                    Institution(
                        name=aff,
                        category=InstitutionCategory.unknown,
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
        pth=Path(f"{config.cache}/arxiv/{arxiv_id}.pdf"),
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
        pth=Path(f"{config.cache}/openreview/{openreview_id}.pdf"),
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
        [[paper]] = self.db.session.execute(pq)

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
