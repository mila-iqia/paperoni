import json
import operator
import re
import traceback
import urllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from operator import itemgetter
from types import SimpleNamespace

from coleo import Option, tooled
from fake_useragent import UserAgent
from ovld import ovld
from sqlalchemy import select

from ...config import papconf
from ...db import schema as sch
from ...fulltext.download import PDF
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
from .pdf_affiliations import find_fulltext_affiliations

ua = UserAgent()
refiners = defaultdict(list)


@dataclass
class Refiner:
    type: str
    fn: object
    priority: float
    needs_paper: bool


@keyword_decorator
def refiner(fn, *, type, priority, needs_paper=False):
    refiners[type].append(
        Refiner(
            type=type,
            priority=priority,
            fn=fn,
            needs_paper=needs_paper,
        )
    )
    return fn


def _extract_date_from_xml(node):
    if node is None:
        return None

    y = node.find("year")
    if y is not None:
        m = node.find("month")
        d = node.find("day")
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
        return date
    else:
        date_node = node.find("string-date")
        if date_node:
            return extract_date(date_node.text)
        else:
            return None


def _paper_from_jats(soup, links):
    selectors = [
        'pub-date[pub-type="ppub"]',
        'pub-date[date-type="pub"]',
        'pub-date[date-type="pub"]',
        'pub-date[pub-type="epub"]',
        "pub-date",
    ]
    date_candidates = [
        result
        for selector in selectors
        if (result := _extract_date_from_xml(soup.select_one(selector)))
    ]
    date_candidates.sort(key=lambda x: -x["date_precision"])
    date = date_candidates and date_candidates[0]

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
                    quality=(0.75,),
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
                    publisher=(
                        journal := soup.select_one(
                            "journal-meta publisher-name"
                        )
                    )
                    and journal.text,
                    links=[],
                    aliases=[],
                ),
                status="preprint" if "rxiv" in jname.lower() else "published",
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

    apikey = papconf.get_token("xplore")
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
                    links=(
                        [Link(type="xplore", link=author["id"])]
                        if "id" in author
                        else []
                    ),
                    quality=(0.75,),
                ),
                affiliations=(
                    [
                        Institution(
                            name=author["affiliation"],
                            category=InstitutionCategory.unknown,
                            aliases=[],
                        )
                    ]
                    if "affiliation" in author
                    else []
                ),
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

    if getattr(data, "event", None) or getattr(data, "container-title", None):
        date_parts = None

        if evt := getattr(data, "event", None):
            venue_name = evt["name"]
            venue_type = VenueType.conference
            if "start" in evt:
                date_parts = evt["start"]["date-parts"][0]

        if venue := getattr(data, "container-title", None):
            venue_name = venue[0]
            if data.type == "journal-article":
                venue_type = VenueType.journal
            else:
                venue_type = VenueType.conference

        if not date_parts:
            for field in (
                "published-online",
                "published-print",
                "published",
                "issued",
                "created",
            ):
                if dateholder := getattr(data, field, None):
                    date_parts = dateholder["date-parts"][0]
                    break

        precision = [
            DatePrecision.year,
            DatePrecision.month,
            DatePrecision.day,
        ][len(date_parts) - 1]
        date_parts += [1] * (3 - len(date_parts))
        release = Release(
            venue=Venue(
                aliases=[],
                name=venue_name,
                type=venue_type,
                series=venue_name,
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
                        quality=(0.75,),
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


@refiner(type="doi", priority=100)
def refine_doi_with_datacite(db, paper, link):
    """
    Refine using DataCite.

    More info:
    API call tutorial: https://support.datacite.org/docs/api-get-doi
    API call reference: https://support.datacite.org/reference/get_dois-id
    DataCite metadata properties: https://datacite-metadata-schema.readthedocs.io/en/4.5/properties/
    """
    doi = link.link
    json_data = readpage(
        f"https://api.datacite.org/dois/{doi}?publisher=true&affiliation=true",
        format="json",
    )
    if "errors" in json_data:
        with covguard():
            return None

    # Mapping to convert DataCite resource type to Paperoni venue type.
    # May be improved.
    item_type_to_venue_type = {
        "Audiovisual": VenueType.unknown,
        "Book": VenueType.book,
        "BookChapter": VenueType.book,
        "Collection": VenueType.unknown,
        "ComputationalNotebook": VenueType.unknown,
        "ConferencePaper": VenueType.conference,
        "ConferenceProceeding": VenueType.conference,
        "DataPaper": VenueType.unknown,
        "Dataset": VenueType.unknown,
        "Dissertation": VenueType.unknown,
        "Event": VenueType.unknown,
        "Image": VenueType.unknown,
        "Instrument": VenueType.unknown,
        "InteractiveResource": VenueType.unknown,
        "Journal": VenueType.journal,
        "JournalArticle": VenueType.journal,
        "Model": VenueType.unknown,
        "OutputManagementPlan": VenueType.unknown,
        "PeerReview": VenueType.review,
        "PhysicalObject": VenueType.unknown,
        "Preprint": VenueType.preprint,
        "Report": VenueType.unknown,
        "Service": VenueType.unknown,
        "Software": VenueType.unknown,
        "Sound": VenueType.unknown,
        "Standard": VenueType.unknown,
        "StudyRegistration": VenueType.unknown,
        "Text": VenueType.unknown,
        "Workflow": VenueType.unknown,
        "Other": VenueType.unknown,
    }

    raw_paper = SimpleNamespace(**json_data["data"]["attributes"])

    # Get paper abstract
    abstract = None
    for desc in raw_paper.descriptions:
        if desc["descriptionType"] == "Abstract":
            abstract = desc["description"]
            break

    # Get paper date, used for paper default release
    for date_info in raw_paper.dates:
        if date_info["dateType"] == "Available":  # Available, or Issued ?
            date_string = date_info["date"]
            date_pieces = date_string.split("-")
            if len(date_pieces) == 1:
                date_available = datetime(
                    year=int(date_pieces[0]), month=1, day=1
                )
                date_precision = DatePrecision.year
            elif len(date_pieces) == 2:
                date_available = datetime(
                    year=int(date_pieces[0]), month=int(date_pieces[1]), day=1
                )
                date_precision = DatePrecision.month
            else:
                date_available = datetime.fromisoformat(date_string)
                date_precision = DatePrecision.day
            break
    else:
        date_available = datetime(
            year=raw_paper.publicationYear, month=1, day=1
        )
        date_precision = DatePrecision.year

    # Try to get paper default release
    releases = [
        Release(
            venue=Venue(
                type=item_type_to_venue_type[
                    raw_paper.types["resourceTypeGeneral"]
                ],
                name=raw_paper.publisher["name"],
                date=date_available,
                date_precision=date_precision,
                series="",
                aliases=[],
                links=[],
            ),
            status="published",
            pages=None,
        )
    ]
    # Try to get more paper releases
    for related_item in raw_paper.relatedItems:
        if (
            related_item["relationType"] == "IsPublishedIn"
            and related_item["relatedItemType"] in item_type_to_venue_type
        ):
            releases.append(
                Release(
                    venue=Venue(
                        type=item_type_to_venue_type[
                            related_item["relatedItemType"]
                        ],
                        name=related_item["titles"][0]["title"],
                        series=related_item["issue"],
                        date=datetime(
                            year=int(related_item["publicationYear"]),
                            month=1,
                            day=1,
                        ),
                        date_precision=DatePrecision.year,
                        volume=related_item["volume"],
                        publisher=related_item["publisher"],
                    ),
                    status="published",
                    pages=f"{related_item['firstPage']}-{related_item['lastPage']}",
                )
            )

    # Get paper default links
    links = [Link(type="doi", link=doi)]
    if raw_paper.url:
        links.append(Link(type="url", link=raw_paper.url))
    for content_url in raw_paper.contentUrl or ():
        links.append(Link(type="contentUrl", link=content_url))
    # Try to get more paper links
    for related_identifier in raw_paper.relatedIdentifiers:
        identifier_type = related_identifier["relatedIdentifierType"]
        relation_type = related_identifier["relationType"]
        identifier = related_identifier["relatedIdentifier"]
        # Available identifier types:
        # ARK arXiv bibcode DOI EAN13 EISSN Handle IGSN ISBN ISSN ISTC LISSN LSID PMID PURL UPC URL URN w3id
        if identifier_type in {"ARK", "arXiv", "DOI", "PURL", "URL", "w3id"}:
            links.append(
                Link(type=f"{relation_type}.{identifier_type}", link=identifier)
            )

    with covguard():
        return Paper(
            title=raw_paper.titles[0]["title"],
            abstract=abstract,
            authors=[
                PaperAuthor(
                    author=Author(
                        name=f"{creator['givenName']} {creator['familyName']}",
                        roles=[],
                        aliases=[],
                        links=[],
                    ),
                    affiliations=[
                        Institution(
                            name=affiliation["name"],
                            category=InstitutionCategory.unknown,
                            aliases=[],
                        )
                        for affiliation in creator["affiliation"]
                    ],
                )
                for creator in raw_paper.creators
            ],
            releases=releases,
            topics=[
                Topic(name=subject["subject"]) for subject in raw_paper.subjects
            ],
            links=links,
            citation_count=raw_paper.citationCount,
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


@refiner(type="dblp", priority=90)
@covguard_fn
def refine_with_dblp(db, paper, link):
    if "/corr/" in link.link:
        return None

    data = readpage(
        f"https://dblp.uni-trier.de/rec/{link.link}.xml", format="xml"
    )
    ee = data.find("ee")
    extra_links = []
    if ee and ee.text.startswith("https://doi.org/"):
        doi = ee.text.replace("https://doi.org/", "")
        extra_links = [Link(type="doi", link=doi)]
    elif ee:
        extra_links = [Link(type="html", link=ee.text)]
    return Paper(
        title=data.find("title").text,
        abstract="",
        authors=[
            PaperAuthor(
                author=Author(
                    name=author.text,
                    roles=[],
                    aliases=[],
                    links=(
                        [Link(type="orcid", link=orcid)]
                        if (orcid := author.attrs.get("orcid", None))
                        else []
                    ),
                    quality=(0,),
                ),
                affiliations=[],
            )
            for author in data.select("author")
        ],
        links=[Link(type=link.type, link=link.link), *extra_links],
        releases=[
            Release(
                venue=Venue(
                    name=(
                        jname := (
                            data.find("booktitle") or data.find("journal")
                        ).text
                    ),
                    series=jname,
                    type=VenueType.journal,
                    date=datetime(
                        year=int(data.find("year").text), month=1, day=1
                    ),
                    date_precision=DatePrecision.year,
                    publisher=None,
                    links=[],
                    aliases=[],
                ),
                status="published",
                pages=(pg := data.find("pages")) and pg.text,
            )
        ],
        topics=[],
        quality=(0,),
    )


# @refiner(type="doi", priority=111)
# def refine_with_springer(db, paper, link):
#     doi = link.link
#     apikey = papconf.get_token("springer")
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


_institutions = [None, None]


def _pdf_refiner(db, paper, link):
    doc = PDF(
        title=paper.title,
        identifier=paper.paper_id.hex(),
        refs=[f"{link.type}:{link.link}"],
    ).get_document()
    if not doc:
        return None

    if _institutions[0] is not db:
        _institutions[:] = [db, {}]
        for (inst,) in db.session.execute(select(sch.Institution)):
            with covguard():
                _institutions[1].update({alias: inst for alias in inst.aliases})

    author_affiliations = find_fulltext_affiliations(
        paper, doc, _institutions[1]
    )

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
                    (
                        aff
                        if isinstance(aff, Institution)
                        else UniqueInstitution(
                            institution_id=aff.institution_id,
                            name=aff.name,
                            category=aff.category,
                            aliases=[],
                        )
                    )
                    for aff in sorted(
                        affiliations, key=lambda x: getattr(x, "name", None)
                    )
                ],
            )
            for author, affiliations in author_affiliations.items()
        ],
        links=[Link(type=link.type, link=link.link)],
        releases=[],
        topics=[],
        quality=(0,),
    )


@refiner(type="arxiv", priority=7, needs_paper=True)
def refine_with_arxiv(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="doi", priority=6, needs_paper=True)
def refine_with_pdf_url_from_crossref(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="openreview", priority=5, needs_paper=True)
def refine_with_openreview(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


@refiner(type="pdf", priority=5, needs_paper=True)
def refine_with_pdf_link(db, paper, link):
    with covguard():
        return _pdf_refiner(db=db, paper=paper, link=link)


class Refiner(BaseScraper):
    def _iterate_refiners(self, links):
        _refiners = []
        for link in links:
            _refiners.extend(
                [(refiner, link) for refiner in refiners.get(link.type, [])]
            )
        _refiners.sort(reverse=True, key=lambda data: data[0].priority)
        for refiner, link in _refiners:
            with Doing(refine=f"{link.type}:{link.link}"):
                yield link, refiner

    def _refine(self, paper, links):
        for link, refiner in self._iterate_refiners(links):
            if paper is None and refiner.needs_paper:
                continue
            try:
                if result := refiner.fn(self.db, paper, link):
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
                title=paper.title if paper else (merged.title or result.title),
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
        try:
            [[paper], *_] = self.db.session.execute(pq)
        except ValueError:
            paper = None

        for _, entry in self.refine(
            paper,
            merge=not separate,
            links=paper.links if paper else [Link(type=type, link=link)],
        ):
            yield entry

    @tooled
    def acquire(self):
        processed_cache = set()

        def been_processed(l):
            tag = f"{l.type}:{l.link}"
            if tag in processed_cache:
                return True
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
                tag = f"{l.type}:{l.link}"
                processed_cache.add(tag)
                yield ScraperData(
                    scraper="refine",
                    tag=tag,
                    data="",
                    date=now,
                )

            i += 1

        yield from []

    @tooled
    def prepare(self):  # pragma: no cover
        pass


__scrapers__ = {"refine": Refiner}
