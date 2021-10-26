import json
import urllib.parse

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
        self.conn = HTTPSAcquirer("api.semanticscholar.org")

    def _evaluate(self, path: str, fields: tuple = None, **params):
        params = {k: v for k, v in params.items() if v is not None}
        if fields is not None:
            params["fields"] = ",".join(fields)
        params = urllib.parse.urlencode(params)
        data = self.conn.get(f"/graph/v1/{path}?{params}")
        jdata = json.loads(data)
        if "error" in jdata:
            raise QueryError(jdata["error"])
        return jdata

    def search(
        self, query, offset=0, limit=100, fields=SEARCH_FIELDS,
    ):
        # {total: str, offset: int, next: optinal int, data: [...]}
        return self._evaluate(
            "paper/search",
            query=query,
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper(self, paper_id, fields=PAPER_FIELDS):
        # paper dict
        return self._evaluate(f"paper/{paper_id}", fields=fields)

    def paper_authors(
        self, paper_id, offset=0, limit=100, fields=PAPER_AUTHORS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self._evaluate(
            f"paper/{paper_id}/authors",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper_citations(
        self, paper_id, offset=0, limit=100, fields=PAPER_CITATIONS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self._evaluate(
            f"paper/{paper_id}/citations",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper_references(
        self, paper_id, offset=0, limit=100, fields=PAPER_REFERENCES_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self._evaluate(
            f"paper/{paper_id}/citations",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def author(self, author_id, fields=AUTHOR_FIELDS):
        # author dict
        return self._evaluate(f"author/{author_id}", fields=fields)

    def author_papers(
        self, author_id, offset=0, limit=100, fields=AUTHOR_PAPERS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self._evaluate(
            f"author/{author_id}/papers",
            offset=offset,
            limit=limit,
            fields=fields,
        )
