import sys
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial

from ..config import config
from ..model import (
    Author,
    DatePrecision,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
    Release,
    Topic,
    Venue,
    VenueType,
)
from ..model.focus import Focus, Focuses
from ..model.merge import qual
from ..utils import soft_fail
from .base import Discoverer, QueryError

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
    "Dataset": VenueType.dataset,
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
        "publicationVenue",
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
    return fields if parent is None else tuple(f"{parent}.{field}" for field in fields)


def _paper_short_fields(parent=None):
    fields = (
        "paperId",
        "url",
        "title",
        "venue",
        "year",
        "authors",  # {authorId, name}
    )
    return fields if parent is None else tuple(f"{parent}.{field}" for field in fields)


def _author_fields(parent=None):
    fields = (
        "authorId",
        "externalIds",
        "url",
        "name",
        "affiliations",
        "homepage",
        "paperCount",
        "citationCount",
    )
    return fields if parent is None else tuple(f"{parent}.{field}" for field in fields)


def _date_from_data(data):
    if pubd := data["publicationDate"]:
        return {
            "date": datetime.strptime(pubd, "%Y-%m-%d").date(),
            "date_precision": DatePrecision.day,
        }
    else:
        return DatePrecision.assimilate_date(data["year"])


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


@dataclass
class SemanticScholar(Discoverer):
    api_key: str = field(default_factory=lambda: config.api_keys.semantic_scholar)

    async def _evaluate(self, path: str, **params):
        jdata = await config.fetch.aread_retry(
            f"https://api.semanticscholar.org/graph/v1/{path}",
            params=params,
            headers={"x-api-key": self.api_key and str(self.api_key)},
            format="json",
        )
        if jdata is None or "error" in jdata:
            raise QueryError(jdata["error"] if jdata else "Received bad JSON")
        return jdata

    async def _list(
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
            results = await self._evaluate(path, offset=next_offset, **params)
            next_offset = results.get("next", None)
            if "data" not in results:
                print("Could not get data:", results["message"])
                return
            for entry in results["data"]:
                yield entry

    def _wrap_paper_author(self, data):
        return PaperAuthor(
            affiliations=[],
            author=(au := self._wrap_author(data)),
            display_name=au.name,
        )

    def _wrap_author(self, data):
        lnk = (aid := data["authorId"]) and Link(type="semantic_scholar", link=aid)
        return Author(
            name=data["name"],
            aliases=[data["name"]],
            links=[lnk] if lnk else [],
            # roles=[],
        )

    def _wrap_paper(self, data):
        links = [Link(type="semantic_scholar", link=data["paperId"])]
        for typ, ref in data["externalIds"].items():
            links.append(
                Link(type=external_ids_mapping.get(t := typ.lower(), t), link=str(ref))
            )
        if data["openAccessPdf"] and (url := data["openAccessPdf"]["url"]):
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
            is_preprint = "rxiv" in data.get("venue", data.get("journal", "")).lower()
            release = Release(
                venue=Venue(
                    type=venue_type_mapping[
                        (pubt := data.get("publicationTypes", [])) and pubt[0] or "_"
                    ],
                    name=data["venue"],
                    series=data["venue"],
                    volume=(j := data["journal"]) and j.get("volume", None),
                    **_date_from_data(data),
                    aliases=[],
                    links=[],
                ),
                status="preprint" if is_preprint else "published",
                pages=None,
            )

        paper = Paper(
            links=links,
            authors=qual(authors, -10.0),
            title=qual(data["title"], -10.0),
            abstract=data["abstract"] or "",
            # citation_count=data["citationCount"],
            topics=[Topic(name=field) for field in (data["fieldsOfStudy"] or ())],
            releases=[release],
        )

        # Create unique key based on Semantic Scholar paper ID
        paper_key = f"semantic_scholar:{data['paperId']}"

        return PaperInfo(
            key=paper_key,
            acquired=datetime.now(),
            paper=paper,
            info={"discovered_by": {"semantic_scholar": data["paperId"]}},
        )

    async def search(self, query, fields=SEARCH_FIELDS, **params):
        papers = self._list(
            "paper/search",
            query=query,
            fields=fields,
            **params,
        )
        async for paper in papers:
            yield self._wrap_paper(paper)

    async def paper(self, paper_id, fields=PAPER_FIELDS):
        return self._wrap_paper(
            await self._evaluate(f"paper/{paper_id}", fields=",".join(fields))
        )

    async def paper_authors(self, paper_id, fields=PAPER_AUTHORS_FIELDS, **params):
        async for author in self._list(
            f"paper/{paper_id}/authors", fields=fields, **params
        ):
            yield author

    async def paper_citations(self, paper_id, fields=PAPER_CITATIONS_FIELDS, **params):
        async for citation in self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        ):
            yield citation

    async def paper_references(self, paper_id, fields=PAPER_REFERENCES_FIELDS, **params):
        async for ref in self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        ):
            yield ref

    async def author(self, name=None, author_id=None, fields=AUTHOR_FIELDS, **params):
        wrap_author = partial(self._wrap_author)
        if name:
            name = name.replace("-", " ")
            authors = self._list("author/search", query=name, fields=fields, **params)
            async for author in authors:
                yield wrap_author(author)
        else:
            yield wrap_author(
                await self._evaluate(
                    f"author/{author_id}", fields=",".join(fields), **params
                )
            )

    async def author_with_papers(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list("author/search", query=name, fields=fields, **params)
        async for author in authors:
            yield (
                self._wrap_author(author),
                [self._wrap_paper(p) for p in author["papers"]],
            )

    async def author_papers(self, author_id, fields=AUTHOR_PAPERS_FIELDS, **params):
        papers = self._list(f"author/{author_id}/papers", fields=fields, **params)
        async for paper in papers:
            yield self._wrap_paper(paper)

    async def query(
        self,
        # Author of the article
        author: str = None,
        # Title of the article
        title: str = None,
        # Maximal number of results per query
        block_size: int = 100,
        # Maximal number of results to return
        limit: int = 10000,
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query semantic scholar"""
        if focuses:
            if limit is not None:
                print(
                    "The 'limit' parameter is ignored when 'focuses' are provided.",
                    file=sys.stderr,
                )

            for focus in focuses.focuses:
                with soft_fail(f"Discovery of {focus}"):
                    match focus:
                        case Focus(drive_discovery=False):
                            continue
                        case Focus(type="author", name=name, score=score):
                            async for paper in self.query(
                                author=name, title=title, block_size=block_size
                            ):
                                paper.score = score
                                yield paper
            return

        if isinstance(author, list):
            author = " ".join(author)
        if isinstance(title, list):
            title = " ".join(title)

        if author and title:
            raise QueryError("Cannot query both author and title")

        if title:
            async for paper in self.search(title, block_size=block_size, limit=limit):
                yield paper

        elif author:
            async for _, papers in self.author_with_papers(
                author, block_size=block_size, limit=limit
            ):
                for paper in papers:
                    yield paper
