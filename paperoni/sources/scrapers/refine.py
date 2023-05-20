import json
import operator
import os
import re
import traceback
import urllib
from collections import defaultdict
from datetime import datetime
from functools import reduce
from operator import itemgetter
from types import SimpleNamespace

from coleo import Option, tooled
from ovld import ovld
from sqlalchemy import select
from fake_useragent import UserAgent

from ...config import config
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
    ScraperData,
    Topic,
    UniqueAuthor,
    UniqueInstitution,
    Venue,
    VenueType,
)
from ...utils import (
    Doing,
    covguard,
    covguard_fn,
    extract_date,
    keyword_decorator,
)
from ..acquire import readpage
from .base import BaseScraper
from .pdftools import PDF, find_fulltext_affiliations

ua = UserAgent()
refiners = defaultdict(list)


@keyword_decorator
def refiner(fn, *, type, priority):
    refiners[type].append((priority, fn))
    return fn


def _only_if_affiliations(paper):
    if paper and any(auth.affiliations for auth in paper.authors):
        return paper
    return None


def _paper_from_jats(soup, links):
    date1 = soup.select_one('pub-date[date-type="pub"] string-date')
    if date1:
        with covguard():
            date = extract_date(date1.text)
    else:
        date2 = (
            soup.select_one('pub-date[pub-type="ppub"]')
            or soup.select_one('pub-date[date-type="pub"]')
            or soup.select_one('pub-date[pub-type="epub"]')
        )
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

    def find_affiliation(aff):
        node = soup.select_one(f'aff#{aff.attrs["rid"]} institution')
        if not node:
            with covguard():
                node = soup.select_one(f'aff#{aff.attrs["rid"]}')
        name = node.text
        name = re.sub(pattern="^[0-9]+", string=name, repl="")
        return Institution(
            name=name,
            category=InstitutionCategory.unknown,
            aliases=[],
        )

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
                    find_affiliation(aff)
                    for aff in author.select('xref[ref-type="aff"]')
                ],
            )
            for author in soup.select('contrib[contrib-type="author"]')
            if author.find("surname")
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


@refiner(type="doi", priority=190)
def refine_doi_with_ieeexplore(db, paper, link):
    doi = link.link
    if not doi.startswith("10.1109/"):
        return None

    apikey = config.get().get_token("xplore")
    if not apikey:  # pragma: no cover
        # TODO: log
        return None

    data = readpage(
        f"http://ieeexploreapi.ieee.org/api/v1/search/articles?apikey={apikey}&format=json&max_records=25&start_record=1&sort_order=asc&sort_field=article_number&doi={doi}",
        format="json",
    )
    (data,) = data["articles"]

    topics = []
    for _, terms in data["index_terms"].items():
        topics.extend(Topic(name=term) for term in terms["terms"])

    if "publication_date" in data:
        extracted_date = extract_date(data["publication_date"])
    else:
        extracted_date = extract_date(data["publication_year"])

    return Paper(
        title=data["title"],
        authors=[
            PaperAuthor(
                author=Author(
                    name=author["full_name"],
                    roles=[],
                    aliases=[],
                    links=[Link(type="xplore", link=author["id"])]
                    if "id" in author
                    else [],
                ),
                affiliations=[
                    Institution(
                        name=author["affiliation"],
                        category=InstitutionCategory.unknown,
                        aliases=[],
                    )
                ]
                if "affiliation" in author
                else [],
            )
            for author in sorted(
                data["authors"]["authors"], key=itemgetter("author_order")
            )
        ],
        abstract=data["abstract"],
        links=[Link(type="doi", link=doi)],
        topics=topics,
        releases=[
            Release(
                venue=Venue(
                    name=(jname := data["publication_title"]),
                    series=jname,
                    type=VenueType.journal,
                    **extracted_date,
                    publisher=data["publisher"],
                    links=[],
                    aliases=[],
                    volume=data.get("volume", None),
                ),
                status="published",
                pages=f"{data['start_page']}-{data['end_page']}",
            )
        ],
        quality=(0,),
    )


@refiner(type="doi", priority=100)
def refine_doi_with_crossref(db, paper, link):
    doi = link.link
    if "arXiv" in doi:
        with covguard():
            return None

    data = readpage(f"https://api.crossref.org/v1/works/{doi}", format="json")

    if data["status"] != "ok":
        with covguard():
            return None
    data = SimpleNamespace(**data["message"])

    if evt := getattr(data, "event", None):
        if "start" in evt:
            date_parts = evt["start"]["date-parts"][0]
        else:
            for field in (
                "published-print",
                "published",
                "published-online",
                "created",
            ):
                if dateholder := getattr(data, field, None):
                    date_parts = dateholder["date-parts"][0]
        precision = [
            DatePrecision.year,
            DatePrecision.month,
            DatePrecision.day,
        ][len(date_parts) - 1]
        date_parts += [1] * (3 - len(date_parts))
        release = Release(
            venue=Venue(
                aliases=[],
                name=evt["name"],
                type=VenueType.conference,
                series=evt["name"],
                links=[],
                open=False,
                peer_reviewed=False,
                publisher=None,
                date_precision=precision,
                date=datetime(*date_parts),
                quality=(1,),
            ),
            status="published",
            pages=None,
        )
        releases = [release]
    else:
        releases = []

    with covguard():
        required_keys = {"given", "family", "affiliation"}
        # TODO: some affiliations are given by ROR id...
        # for example: {'id': [{'id': 'https://ror.org/03cve4549', 'id-type': 'ROR', 'asserted-by': 'publisher'}]}
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
                        if "name" in aff
                    ],
                )
                for author in data.author
                if not (required_keys - author.keys())
            ],
            abstract="",
            links=[Link(type="doi", link=doi)],
            topics=[],
            releases=releases,
            quality=(0,),
        )


@refiner(type="doi", priority=190)
def refine_doi_with_biorxiv(db, paper, link):
    doi = link.link
    if not doi.startswith("10.1101/"):
        return None

    data = readpage(
        f"https://api.biorxiv.org/details/biorxiv/{doi}", format="json"
    )

    if {"status": "ok"} not in data["messages"] or not data["collection"]:
        with covguard():
            return None

    jats = data["collection"][0]["jatsxml"]

    return _paper_from_jats(
        readpage(jats, format="xml"),
        links=[Link(type="doi", link=doi)],
    )


@ovld
def _sd_find(d: dict, tag, indices):
    if d.get("#name", None) == tag:
        for idx in indices:
            d = d[idx]
        return [d]
    return _sd_find(list(d.values()), tag, indices)


@ovld
def _sd_find(li: list, tag, indices):
    results = []
    for v in li:
        results += _sd_find(v, tag, indices)
    return results


@ovld
def _sd_find(x, tag, indices):
    return []


def _sd_find_one(x, tag, indices=[]):
    return _sd_find(x, tag, indices)[0]


@refiner(type="doi", priority=90)
def refine_doi_with_sciencedirect(db, paper, link):
    doi = link.link
    if not doi.startswith("10.1016/"):
        with covguard():
            return None

    info = readpage(f"https://doi.org/api/handles/{doi}", format="json")
    url1 = [v for v in info["values"] if v["type"] == "URL"][0]["data"]["value"]
    redirector = readpage(url1, format="html")
    url2 = redirector.select_one("#redirectURL").attrs["value"]
    url2 = urllib.parse.unquote(url2)
    if "sciencedirect" not in url2:
        with covguard():
            return

    soup = readpage(url2, format="html", headers={"User-Agent": ua.chrome})
    data = json.loads(soup.select_one('script[type="application/json"]').text)

    authors_raw = _sd_find(data["authors"], "author", [])
    aff_raw = {
        aff["$"].get("id", "n/a"): aff
        for aff in _sd_find(data["authors"], "affiliation", [])
    }

    authors = []
    for author in authors_raw:
        given = _sd_find_one(author, "given-name", "_")
        surname = _sd_find_one(author, "surname", "_")
        name = f"{given} {surname}"
        affids = [
            x
            for x in _sd_find(author, "cross-ref", ("$", "refid"))
            if x.startswith("af")
        ]
        affs = [
            _sd_find(aff_raw[affid], "organization", "_") for affid in affids
        ]
        affs = reduce(operator.add, affs, [])
        authors.append(
            PaperAuthor(
                author=Author(
                    name=name,
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
                    for aff in affs
                ],
            )
        )

    return Paper(
        title=_sd_find_one(data["article"], "title", "_"),
        abstract="",
        authors=authors,
        links=[Link(type=link.type, link=link.link)],
        releases=[],
        topics=[],
        quality=(0,),
    )


@refiner(type="pmc", priority=110)
@covguard_fn
def refine_with_pubmedcentral(db, paper, link):
    pmc_id = link.link
    soup = readpage(
        f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm",
        format="xml",
    )
    return _paper_from_jats(
        soup,
        links=[Link(type="pmc", link=pmc_id)],
    )


# @refiner(type="doi", priority=111)
# def refine_with_springer(db, paper, link):
#     doi = link.link
#     apikey = config.get().get_token("springer")
#     # apikey = os.environ.get("SPRINGER_API_KEY", None)
#     if not apikey or not doi.startswith("10.1007/"):
#         return None

#     soup = readpage(
#         f"https://api.springernature.com/meta/v2/jats?q=doi:{doi}&api_key={apikey}",
#         format="xml",
#     )
#     return _paper_from_jats(
#         soup,
#         links=[Link(type="doi", link=doi)],
#     )


_institutions = None


def _pdf_refiner(db, paper, link):
    global _institutions

    doc = PDF(link).get_document()
    if not doc:
        return None

    if _institutions is None:
        _institutions = {}
        for (inst,) in db.session.execute(select(sch.Institution)):
            with covguard():
                _institutions.update({alias: inst for alias in inst.aliases})

    author_affiliations = find_fulltext_affiliations(paper, doc, _institutions)

    if not author_affiliations:
        with covguard():
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
                    aff
                    if isinstance(aff, Institution)
                    else UniqueInstitution(
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


@refiner(type="arxiv", priority=7)
def refine_with_arxiv(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="doi", priority=6)
def refine_with_pdf_url_from_crossref(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="openreview", priority=5)
def refine_with_openreview(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="pdf", priority=5)
def refine_with_pdf_link(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


class Refiner(BaseScraper):
    def _iterate_refiners(self, links):
        _refiners = []
        for link in links:
            _refiners.extend(
                [(p, link, r) for (p, r) in refiners.get(link.type, [])]
            )
        _refiners.sort(reverse=True, key=lambda data: data[0])
        for _, link, refiner in _refiners:
            with Doing(refine=f"{link.type}:{link.link}"):
                yield link, refiner

    def _refine(self, paper, links):
        for link, refiner in self._iterate_refiners(links):
            try:
                if result := refiner(self.db, paper, link):
                    yield refiner, result
            except Exception as e:
                with covguard():
                    traceback.print_exception(e)

    def refine(self, paper, merge=False, links=None):
        def uniq(entries):
            rval = []
            for entry in entries:
                if entry not in rval:
                    rval.append(entry)
            return rval

        results = list(
            self._refine(paper, links=paper.links if links is None else links)
        )
        if not merge or not results:
            return results

        (_, merged), *rest = results

        for _, result in rest:
            already_has_affs = any(auth.affiliations for auth in merged.authors)
            merged = Paper(
                title=paper.title,
                abstract=merged.abstract or result.abstract,
                authors=merged.authors if already_has_affs else result.authors,
                links=uniq([*merged.links, *result.links]),
                releases=merged.releases or result.releases,
                topics=uniq([*merged.topics, *result.topics]),
                quality=merged.quality,
            )

        return [("refine", merged)]

    @tooled
    def query(
        self,
        # Link to query
        link: Option = None,
        separate: Option & bool = False,
    ):
        type, link = link.split(":", 1)
        pq = (
            select(sch.Paper)
            .join(sch.PaperLink)
            .filter(sch.PaperLink.type == type, sch.PaperLink.link == link)
        )
        [[paper], *_] = self.db.session.execute(pq)

        for _, entry in self.refine(paper, merge=not separate):
            yield entry

    @tooled
    def acquire(self):
        def been_processed(l):
            tag = f"{l.type}:{l.link}"
            pq = (
                select(sch.ScraperData)
                .filter(sch.ScraperData.scraper == "refine")
                .filter(sch.ScraperData.tag == tag)
            )
            for _ in self.db.session.execute(pq):
                return True
            return False

        limit: Option & int = None

        now = datetime.now()

        # Select all papers and order them from most recent
        pq = select(sch.Paper).distinct(sch.Paper.paper_id)
        pq = pq.join(sch.Paper.release).join(sch.Release.venue)
        pq = pq.order_by(sch.Venue.date.desc())

        papers = self.db.session.execute(pq)

        i = 0
        for (paper,) in papers:
            if limit and (i == limit):
                break

            links = [l for l in paper.links if not been_processed(l)]

            if not links:
                continue

            print(i, paper.title)

            for _, result in self.refine(paper, merge=True, links=links):
                yield result

            for l in links:
                yield ScraperData(
                    scraper="refine",
                    tag=f"{l.type}:{l.link}",
                    data="",
                    date=now,
                )

            i += 1

        yield from []

    @tooled
    def prepare(self):  # pragma: no cover
        pass


__scrapers__ = {"refine": Refiner}
