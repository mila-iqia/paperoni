import json
import urllib.parse
from datetime import datetime

from coleo import Option, tooled

from ...utils import QueryError
from ..acquire import HTTPSAcquirer
from ..model import (
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
from ..utils import prepare

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


class SemanticScholarQueryManager:
    # "authors" will have fields "authorId" and "name"
    SEARCH_FIELDS = _paper_long_fields(extras=("authors",))
    PAPER_FIELDS = (
        *_paper_long_fields(),
        *_author_fields(parent="authors"),
        *_paper_short_fields(parent="citations"),
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
        + _paper_short_fields(parent="citations")
        + _paper_short_fields(parent="references")
    )

    def __init__(self):
        self.conn = HTTPSAcquirer(
            "api.semanticscholar.org",
            delay=5 * 60 / 100,  # 100 requests per 5 minutes
        )

    def _evaluate(self, path: str, **params):
        params = urllib.parse.urlencode(params)
        data = self.conn.get(f"/graph/v1/{path}?{params}")
        jdata = json.loads(data)
        if "error" in jdata:
            raise QueryError(jdata["error"])
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
        authors = list(map(self._wrap_paper_author, data["authors"]))
        # date = data["publicationDate"] or f'{data["year"]}-01-01'
        if pubd := data["publicationDate"]:
            date = {
                "date": f"{pubd} 00:00",
                "date_precision": DatePrecision.day,
            }
        else:
            date = DatePrecision.assimilate_date(data["year"])
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
                **date,
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

    def paper(self, paper_id, fields=PAPER_FIELDS):
        (paper,) = self._list(f"paper/{paper_id}", fields=fields)
        return paper

    def paper_authors(self, paper_id, fields=PAPER_AUTHORS_FIELDS, **params):
        yield from self._list(
            f"paper/{paper_id}/authors", fields=fields, **params
        )

    def paper_citations(
        self, paper_id, fields=PAPER_CITATIONS_FIELDS, **params
    ):
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def paper_references(
        self, paper_id, fields=PAPER_REFERENCES_FIELDS, **params
    ):
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def author(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list(
            f"author/search", query=name, fields=fields, **params
        )
        yield from map(self._wrap_author, authors)

    def author_with_papers(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list(
            f"author/search", query=name, fields=fields, **params
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


def _between(name, after, before):
    name = name.lower()
    if after and name[: len(after)] <= after:
        return False
    if before and name[: len(before)] >= before:
        return False
    return True


class SemanticScholarScraper:
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
        author = " ".join(author)
        title = " ".join(title)

        if author and title:
            raise QueryError("Cannot query both author and title")

        ss = SemanticScholarQueryManager()

        if title:
            yield from ss.search(title, block_size=block_size, limit=limit)

        elif author:
            for auth in ss.author(author):
                print(auth)

    @tooled
    def acquire(self, queries):
        todo = {}

        after: Option = ""
        before: Option = ""
        name: Option = ""

        if name:
            queries = [
                auq for auq in queries if auq.author.name.lower() == name
            ]
        queries.sort(key=lambda auq: auq.author.name.lower())

        for auq in queries:
            if not _between(auq.author.name, after, before):
                continue
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
            yield from ss.author_papers(ssid, block_size=1000)

    @tooled
    def prepare(self, researchers):
        ss = SemanticScholarQueryManager()
        return prepare(
            researchers,
            idtype="semantic_scholar",
            query_name=ss.author_with_papers,
            minimum=1,
        )


__scrapers__ = {"semantic_scholar": SemanticScholarScraper()}
