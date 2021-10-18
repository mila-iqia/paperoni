import http.client
import json
import urllib.parse

from paperoni.query import QueryError
import pprint


def _print(data):
    pprint.PrettyPrinter(indent=2).pprint(data)


class SemanticScholarQueryManager:
    SEARCH_FIELDS = (
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
        "authors",  # {authorId, name}
    )
    PAPER_FIELDS = (
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
        # "authors",
        "authors.authorId",
        "authors.externalIds",
        "authors.url",
        "authors.name",
        "authors.aliases",
        "authors.affiliations",
        "authors.homepage",
        # "citations",
        "citations.paperId",
        "citations.url",
        "citations.title",
        "citations.venue",
        "citations.year",
        "citations.authors",  # {authorId, name}
        # "references",
        "references.paperId",
        "references.url",
        "references.title",
        "references.venue",
        "references.year",
        "references.authors",  # {authorId, name}
        "embedding",
    )
    PAPER_AUTHORS_FIELDS = (
        "authorId",
        "externalIds",
        "url",
        "name",
        "aliases",
        "affiliations",
        "homepage",
        # "papers",
        "papers.paperId",
        "papers.externalIds",
        "papers.url",
        "papers.title",
        "papers.abstract",
        "papers.venue",
        "papers.year",
        "papers.referenceCount",
        "papers.citationCount",
        "papers.influentialCitationCount",
        "papers.isOpenAccess",
        "papers.fieldsOfStudy",
        "papers.authors",  # {authorId, name}
    )
    PAPER_CITATIONS_FIELDS = (
        "contexts",
        "intents",
        "isInfluential",
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
        "authors",  # {authorId, name}
    )
    PAPER_REFERENCES_FIELDS = PAPER_CITATIONS_FIELDS
    AUTHOR_FIELDS = PAPER_AUTHORS_FIELDS
    AUTHOR_PAPERS_FIELDS = (
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
        "authors",  # {authorId, name}
        # "citations",
        "citations.paperId",
        "citations.url",
        "citations.title",
        "citations.venue",
        "citations.year",
        "citations.authors",  # {authorId, name}
        # "references",
        "references.paperId",
        "references.url",
        "references.title",
        "references.venue",
        "references.year",
        "references.authors",  # {authorId, name}
    )

    def __init__(self):
        self.conn = http.client.HTTPSConnection("api.semanticscholar.org")

    def evaluate(self, path: str, fields: tuple = None, **params):
        params = {k: v for k, v in params.items() if v is not None}
        if fields is not None:
            params["fields"] = ",".join(fields)
        params = urllib.parse.urlencode(params)
        self.conn.request("GET", f"/graph/v1/{path}?{params}")
        response = self.conn.getresponse()
        data = response.read()
        jdata = json.loads(data)
        if "error" in jdata:
            raise QueryError(jdata["error"])
        return jdata

    def search(
        self, query, offset=0, limit=100, fields=SEARCH_FIELDS,
    ):
        # {total: str, offset: int, next: optinal int, data: [...]}
        return self.evaluate(
            "paper/search",
            query=query,
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper(self, paper_id, fields=PAPER_FIELDS):
        # paper dict
        return self.evaluate(f"paper/{paper_id}", fields=fields)

    def paper_authors(
        self, paper_id, offset=0, limit=100, fields=PAPER_AUTHORS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self.evaluate(
            f"paper/{paper_id}/authors",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper_citations(
        self, paper_id, offset=0, limit=100, fields=PAPER_CITATIONS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self.evaluate(
            f"paper/{paper_id}/citations",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def paper_references(
        self, paper_id, offset=0, limit=100, fields=PAPER_REFERENCES_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self.evaluate(
            f"paper/{paper_id}/citations",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def author(self, author_id, fields=AUTHOR_FIELDS):
        # author dict
        return self.evaluate(f"author/{author_id}", fields=fields)

    def author_papers(
        self, author_id, offset=0, limit=100, fields=AUTHOR_PAPERS_FIELDS,
    ):
        # {offset: int, next: optional int, data: [...]}
        return self.evaluate(
            f"author/{author_id}/papers",
            offset=offset,
            limit=limit,
            fields=fields,
        )

    def test(self):
        # print(self.search("paleontology", fields=()))
        # _print(self.paper("84deebbb20d312acc58785cf58a9e5dd445b4cf4"))
        # _print(self.paper_authors("84deebbb20d312acc58785cf58a9e5dd445b4cf4"))
        # _print(self.paper_citations("84deebbb20d312acc58785cf58a9e5dd445b4cf4"))
        # _print(self.paper_references("84deebbb20d312acc58785cf58a9e5dd445b4cf4"))
        # _print(self.author("11557131"))
        _print(self.author_papers("11557131"))


SemanticScholarQueryManager().test()
