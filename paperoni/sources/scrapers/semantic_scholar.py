import re
import time
from datetime import datetime

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
    Topic,
    Venue,
    VenueType,
)
from ...utils import QueryError
from ..acquire import HTTPSAcquirer
from ..helpers import (
    filter_researchers_interface,
    prepare_interface,
    prompt_controller,
)
from .base import BaseScraper

external_ids_mapping = {
    "pubmedcentral": "pmc",
}


venue_type_mapping = {
    "JournalArticle": VenueType.journal,
    "Conference": VenueType.conference,
    "Book": VenueType.book,
    "Review": VenueType.review,
    "News": VenueType.news,
    "Study": VenueType.study,
    "MetaAnalysis": VenueType.meta_analysis,
    "Editorial": VenueType.editorial,
    "LettersAndComments": VenueType.letters_and_comments,
    "CaseReport": VenueType.case_report,
    "ClinicalTrial": VenueType.clinical_trial,
    "_": VenueType.unknown,
}


def _paper_long_fields(parent=None, extras=()):
    fields = (
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "venue",
        "publicationTypes",
        "publicationDate",
        "year",
        "journal",
        "referenceCount",
        "citationCount",
        "influentialCitationCount",
        "isOpenAccess",
        "openAccessPdf",
        "fieldsOfStudy",
        *extras,
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


def _paper_short_fields(parent=None):
    fields = (
        "paperId",
        "url",
        "title",
        "venue",
        "year",
        "authors",  # {authorId, name}
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


def _author_fields(parent=None):
    fields = (
        "authorId",
        "externalIds",
        "url",
        "name",
        "aliases",
        "affiliations",
        "homepage",
        "paperCount",
        "citationCount",
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


def _date_from_data(data):
    if pubd := data["publicationDate"]:
        return {
            "date": f"{pubd} 00:00",
            "date_precision": DatePrecision.day,
        }
    else:
        return DatePrecision.assimilate_date(data["year"])


def _figure_out_date(data):
    date = _date_from_data(data)

    # The dblp code usually embeds the year at the end, e.g. journals/jojo/Smith21
    # for an article published in 2021. Semantic Scholar may mess up the publication
    # date by picking up the preprint's, so we "fix" it with the dblp code if we can.
    # We have to be careful, though, because e.g. arxiv codes are like
    # journals/corr/abs-2110-01234. It's possible other cases are messed up, we'll
    # take care of it when it happens.
    for typ, ref in data["externalIds"].items():
        if typ.lower() == "dblp" and not ref.startswith("journals/corr/abs-"):
            if m := re.search(pattern=r"([0-9]+)$", string=ref):
                syear = m.groups()[0]
                if len(syear) == 4 or len(syear) == 2:
                    year = int(syear)
                    if 50 < year < 100:
                        year += 1900
                    elif year < 50:
                        year += 2000
                    elif not (1950 <= year <= 2050):  # pragma: no cover
                        continue
                    if (
                        year
                        != datetime.strptime(
                            date["date"], "%Y-%m-%d %H:%M"
                        ).year
                    ):
                        date = {
                            "date": f"{year}-01-01 00:00",
                            "date_precision": DatePrecision.year,
                        }

    return date


class SemanticScholarQueryManager:
    # "authors" will have fields "authorId" and "name"
    SEARCH_FIELDS = _paper_long_fields(extras=("authors",))
    PAPER_FIELDS = (
        *_paper_long_fields(),
        *_author_fields(parent="authors"),
        # *_paper_short_fields(parent="citations"),
        *_paper_short_fields(parent="references"),
        "embedding",
    )
    PAPER_AUTHORS_FIELDS = _author_fields() + _paper_long_fields(
        parent="papers", extras=("authors",)
    )
    PAPER_CITATIONS_FIELDS = (
        "contexts",
        "intents",
        "isInfluential",
        *SEARCH_FIELDS,
    )
    PAPER_REFERENCES_FIELDS = PAPER_CITATIONS_FIELDS
    AUTHOR_FIELDS = PAPER_AUTHORS_FIELDS
    AUTHOR_PAPERS_FIELDS = (
        SEARCH_FIELDS
        # + _paper_short_fields(parent="citations")
        + _paper_short_fields(parent="references")
    )

    def __init__(self):
        self.conn = HTTPSAcquirer(
            "api.semanticscholar.org",
            delay=1.5,  # Wait 1.5 seconds between requests
            format="json",
        )

    def _evaluate(self, path: str, **params):
        jdata = self.conn.get(
            f"/graph/v1/{path}",
            params=params,
            headers={"x-api-key": papconf.get_token("semantic_scholar")},
        )
        if jdata is None or "error" in jdata:  # pragma: no cover
            raise QueryError(jdata["error"] if jdata else "Received bad JSON")
        return jdata

    def _list(
        self,
        path: str,
        fields: tuple[str],
        block_size: int = 100,
        limit: int = 10000,
        **params,
    ):
        params = {
            "fields": ",".join(fields),
            "limit": min(block_size or 10000, limit),
            **params,
        }
        next_offset = 0
        while next_offset is not None and next_offset < limit:
            results = self._evaluate(path, offset=next_offset, **params)
            next_offset = results.get("next", None)
            if "data" not in results:
                print("Could not get data:", results["message"])
                return
            for entry in results["data"]:
                yield entry

    def _wrap_paper_author(self, data):
        return PaperAuthor(
            affiliations=[],
            author=self._wrap_author(data),
        )

    def _wrap_author(self, data):
        lnk = (aid := data["authorId"]) and Link(
            type="semantic_scholar", link=aid
        )
        return Author(
            name=data["name"],
            aliases=data.get("aliases", None) or [],
            links=[lnk] if lnk else [],
            roles=[],
        )

    def _wrap_paper(self, data):
        links = [Link(type="semantic_scholar", link=data["paperId"])]
        for typ, ref in data["externalIds"].items():
            links.append(
                Link(
                    type=external_ids_mapping.get(t := typ.lower(), t), link=ref
                )
            )
        if data["openAccessPdf"]:
            url = data["openAccessPdf"]["url"]
            url = url.replace("://arxiv.org", "://export.arxiv.org")
            links.append(
                Link(
                    type="pdf",
                    link=url,
                )
            )

        authors = list(map(self._wrap_paper_author, data["authors"]))

        if "ArXiv" in data["externalIds"]:
            release = Release(
                venue=Venue(
                    type=VenueType.preprint,
                    name="ArXiv",
                    series="ArXiv",
                    volume=None,
                    **_date_from_data(data),
                    aliases=[],
                    links=[],
                ),
                status="preprint",
                pages=None,
            )

        else:
            release = Release(
                venue=Venue(
                    type=venue_type_mapping[
                        (pubt := data.get("publicationTypes", []))
                        and pubt[0]
                        or "_"
                    ],
                    name=data["venue"],
                    series=data["venue"],
                    volume=(j := data["journal"]) and j.get("volume", None),
                    **_date_from_data(data),
                    aliases=[],
                    links=[],
                ),
                status="published",
                pages=None,
            )

        return Paper(
            links=links,
            authors=authors,
            title=data["title"],
            abstract=data["abstract"] or "",
            citation_count=data["citationCount"],
            topics=[
                Topic(name=field) for field in (data["fieldsOfStudy"] or ())
            ],
            releases=[release],
        )

    def search(self, query, fields=SEARCH_FIELDS, **params):
        papers = self._list(
            "paper/search",
            query=query,
            fields=fields,
            **params,
        )
        yield from map(self._wrap_paper, papers)

    def paper(self, paper_id, fields=PAPER_FIELDS):  # pragma: no cover
        (paper,) = self._list(f"paper/{paper_id}", fields=fields)
        return paper

    def paper_authors(
        self, paper_id, fields=PAPER_AUTHORS_FIELDS, **params
    ):  # pragma: no cover
        yield from self._list(
            f"paper/{paper_id}/authors", fields=fields, **params
        )

    def paper_citations(
        self, paper_id, fields=PAPER_CITATIONS_FIELDS, **params
    ):  # pragma: no cover
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def paper_references(
        self, paper_id, fields=PAPER_REFERENCES_FIELDS, **params
    ):  # pragma: no cover
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def author(self, name, fields=AUTHOR_FIELDS, **params):  # pragma: no cover
        name = name.replace("-", " ")
        authors = self._list(
            f"author/search", query=name, fields=fields, **params
        )
        yield from map(self._wrap_author, authors)

    def author_with_papers(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list(
            "author/search", query=name, fields=fields, **params
        )
        for author in authors:
            yield (
                self._wrap_author(author),
                [self._wrap_paper(p) for p in author["papers"]],
            )

    def author_papers(self, author_id, fields=AUTHOR_PAPERS_FIELDS, **params):
        papers = self._list(
            f"author/{author_id}/papers", fields=fields, **params
        )
        yield from map(self._wrap_paper, papers)


class SemanticScholarScraper(BaseScraper):
    @tooled
    def query(
        self,
        # Author to query
        # [alias: -a]
        # [nargs: +]
        author: Option = [],
        # Title of the paper
        # [alias: -t]
        # [nargs: +]
        title: Option = [],
        # Maximal number of results per query
        block_size: Option & int = 100,
        # Maximal number of results to return
        limit: Option & int = 10000,
    ):
        if isinstance(author, list):
            author = " ".join(author)
        if isinstance(title, list):
            title = " ".join(title)

        if author and title:
            raise QueryError("Cannot query both author and title")

        ss = SemanticScholarQueryManager()

        if title:
            yield from ss.search(title, block_size=block_size, limit=limit)

        elif author:
            for _, papers in ss.author_with_papers(author):
                yield from papers

    @tooled
    def acquire(self):
        queries = self.generate_paper_queries()

        todo = {}

        queries = filter_researchers_interface(
            queries, getname=lambda q: q.author.name
        )

        for auq in queries:
            for link in auq.author.links:
                if link.type == "semantic_scholar":
                    todo[link.link] = auq

        ss = SemanticScholarQueryManager()

        yield Meta(
            scraper="ssch",
            date=datetime.now(),
        )

        for ssid, auq in todo.items():
            print(f"Fetch papers for {auq.author.name} (ID={ssid})")
            time.sleep(5)
            yield from ss.author_papers(ssid, block_size=1000)

    @tooled
    def prepare(self, controller=prompt_controller):
        ss = SemanticScholarQueryManager()
        return prepare_interface(
            researchers=self.generate_author_queries(),
            idtype="semantic_scholar",
            query_name=ss.author_with_papers,
            controller=controller,
            minimum=1,
        )


__scrapers__ = {"semantic_scholar": SemanticScholarScraper}
