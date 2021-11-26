import json
import urllib.parse

from ..papers2 import Author, Link, Paper, Release, Topic, Venue
from ..query import QueryError
from .acquire import HTTPSAcquirer


def _paper_long_fields(parent=None, extras=()):
    fields = (
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "venue",
        "year",
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

    def _list(self, path: str, fields: tuple, block_size: int = 100, **params):
        params = {
            "fields": ",".join(fields),
            "limit": block_size or 10000,
            **params,
        }
        next_offset = 0
        while next_offset is not None:
            results = self._evaluate(path, offset=next_offset, **params)
            next_offset = results.get("next", None)
            for entry in results["data"]:
                yield entry

    def _wrap_author(self, data):
        return Author(
            name=data["name"],
            links=[Link(type="SemanticScholar", ref=data["authorId"])],
        )

    def _wrap_paper(self, data):
        links = [Link(type="SemanticScholar", ref=data["paperId"])]
        for typ, ref in data["externalIds"].items():
            links.append(Link(type=typ, ref=ref))
        authors = list(map(self._wrap_author, data["authors"]))
        release = Release(venue=Venue(code=data["venue"],), year=data["year"],)
        return Paper(
            links=links,
            authors=authors,
            title=data["title"],
            abstract=data["abstract"],
            citation_count=data["citationCount"],
            topics=[
                Topic(name=field) for field in (data["fieldsOfStudy"] or ())
            ],
            releases=[release],
        )

    def search(self, query, fields=SEARCH_FIELDS, **params):
        papers = self._list(
            "paper/search", query=query, fields=fields, **params,
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

    def author(self, author_id, fields=AUTHOR_FIELDS, **params):
        yield from self._list(f"author/{author_id}", fields=fields, **params)

    def author_papers(self, author_id, fields=AUTHOR_PAPERS_FIELDS, **params):
        papers = self._list(
            f"author/{author_id}/papers", fields=fields, **params
        )
        yield from map(self._wrap_paper, papers)
