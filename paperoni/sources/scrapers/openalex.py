import pprint
from datetime import datetime
from typing import Dict, List, Optional

from coleo import tooled, Option

from .base import BaseScraper
from ..acquire import HTTPSAcquirer
from ...model import (
    Paper,
    Release,
    Venue,
    Link,
    Author,
    Topic,
    PaperAuthor,
    Institution,
    InstitutionCategory,
    VenueType,
    DatePrecision,
)
from ...utils import QueryError

# https://docs.openalex.org/api-entities/institutions/institution-object#type
INSTITUTION_CATEGORY_MAPPING = {
    "Education".lower(): InstitutionCategory.academia,
    "Healthcare".lower(): InstitutionCategory.unknown,
    "Company".lower(): InstitutionCategory.industry,
    "Archive".lower(): InstitutionCategory.unknown,
    "Nonprofit".lower(): InstitutionCategory.unknown,
    "Government".lower(): InstitutionCategory.unknown,
    "Facility".lower(): InstitutionCategory.unknown,
    "Other".lower(): InstitutionCategory.unknown,
}

# https://docs.openalex.org/api-entities/sources/source-object#type
VENUE_TYPE_MAPPING = {
    "journal": VenueType.journal,
    "repository": VenueType.unknown,
    "conference": VenueType.conference,
    "ebook platform": VenueType.book,
    "book series": VenueType.book,
    "metadata": VenueType.unknown,
    "other": VenueType.unknown,
}


class OpenAlexQueryManager:
    def __init__(self):
        self.conn = HTTPSAcquirer("api.openalex.org", format="json")

    def find_author_id(self, author: str) -> Optional[str]:
        found = self._evaluate(
            "authors", filter=f"display_name.search:{author}"
        )
        results = found["results"]
        return results[0]["id"] if results else None

    def find_institution_id(self, institution: str) -> Optional[str]:
        found = self._evaluate(
            "institutions", filter=f"display_name.search:{institution}"
        )
        results = found["results"]
        return results[0]["id"] if results else None

    def works(self, **params):
        yield from map(self._try_wrapping_paper, self._list("works", **params))

    def _list(self, path: str, per_page: int = 25, page: int = 1, **params):
        while True:
            local_params = {"page": page, "per-page": per_page, **params}
            results = self._evaluate(path, **local_params)
            if not results["results"]:
                # No more results.
                break
            for entry in results["results"]:
                yield entry
            # Next page
            page += 1

    def _evaluate(self, path: str, **params):
        jdata = self.conn.get(f"/{path}", params=params)
        if jdata is None:
            raise QueryError("Received bad JSON")
        if "message" in jdata:
            if "error" in jdata:
                error_info = (
                    f"[error] {jdata['error']} [message] {jdata['message']}"
                )
            else:
                error_info = jdata["message"]
            raise QueryError(error_info)
        assert "meta" in jdata
        assert "results" in jdata
        return jdata

    def _try_wrapping_paper(self, data: dict) -> Paper:
        try:
            return self._wrap_paper(data)
        except Exception as exc:
            raise Exception(pprint.pformat(data)) from exc

    def _wrap_paper(self, data: dict) -> Paper:
        locations = data["locations"]
        if locations:
            assert locations
            assert locations[0] == data["primary_location"]
        else:
            assert data["primary_location"] is None
            assert data["best_oa_location"] is None

        if data.get("doi"):
            assert data["doi"] == data["ids"]["doi"]

        oa_url = data["open_access"]["oa_url"]

        publication_date = datetime.fromisoformat(data["publication_date"])

        # NB: From locations we can collect links that directly lead to paper.
        # We collect them here so that they can also be added to paper "links" field.
        links_from_locations = []
        for location in locations:
            if location["landing_page_url"]:
                links_from_locations.append(
                    Link(
                        type="url",
                        link=location["landing_page_url"],
                    )
                )
            if location["pdf_url"]:
                links_from_locations.append(
                    Link(type="pdf", link=location["pdf_url"])
                )

        return Paper(
            title=data["display_name"] or "Untilted",
            abstract=self._reconstruct_abstract(
                data["abstract_inverted_index"] or {}
            ),
            authors=[
                PaperAuthor(
                    author=Author(
                        name=authorship["author"]["display_name"],
                        roles=[],
                        aliases=[],
                        links=[
                            Link(
                                type="openalex", link=authorship["author"]["id"]
                            )
                        ]
                        + (
                            [
                                Link(
                                    type="orcid",
                                    link=authorship["author"]["orcid"],
                                )
                            ]
                            if authorship["author"]["orcid"] is not None
                            else []
                        ),
                    ),
                    affiliations=[
                        Institution(
                            name=author_inst["display_name"],
                            category=INSTITUTION_CATEGORY_MAPPING[
                                author_inst["type"]
                            ],
                            aliases=[],
                        )
                        for author_inst in authorship["institutions"]
                    ],
                )
                for authorship in data["authorships"]
            ],
            releases=[
                Release(
                    venue=Venue(
                        type=VENUE_TYPE_MAPPING[location["source"]["type"]],
                        name=location["source"]["display_name"],
                        series="",
                        # NB: Specific publication date for each location does not seem to be available,
                        # so, by default, we use available `Work.publication_date`, defined at Work level.
                        # https://docs.openalex.org/api-entities/works/work-object#publication_date
                        date=publication_date,
                        date_precision=DatePrecision.day,
                        volume=None,
                        publisher=None,
                        aliases=[],
                        links=(
                            [
                                Link(
                                    type="url",
                                    link=location["landing_page_url"],
                                )
                            ]
                            if location["landing_page_url"]
                            else []
                        )
                        + (
                            [Link(type="pdf", link=location["pdf_url"])]
                            if location["pdf_url"] is not None
                            else []
                        ),
                        # NB: I guess "open" mean "an Open Access version of this work is available at this location" ?
                        open=location["is_oa"],
                        # https://docs.openalex.org/api-entities/works/work-object/location-object#version
                        peer_reviewed=(
                            location["version"]
                            in ("acceptedVersion", "publishedVersion")
                        ),
                    ),
                    status=(
                        "published"
                        if location.get("is_published")
                        else (
                            "accepted"
                            if location.get("is_accepted")
                            else "unknown"
                        )
                    ),
                    pages=None,
                )
                for location in locations
                if location["source"]
            ],
            topics=[
                Topic(name=data_concept["display_name"])
                for data_concept in data["concepts"]
            ],
            links=[Link(type=typ, link=ref) for typ, ref in data["ids"].items()]
            + (
                [Link(type="open-access", link=oa_url)]
                if oa_url is not None
                else []
            )
            + links_from_locations,
            citation_count=data["cited_by_count"],
        )

    @classmethod
    def _reconstruct_abstract(cls, inverted: Dict[str, List[int]]) -> str:
        """Reconstruct a string from a {word: idx} dict."""
        idx = {}
        for word, ii in inverted.items():
            for i in ii:
                idx[i] = word
        words = [word for i, word in sorted(idx.items())]
        return " ".join(words)


class OpenAlexScraper(BaseScraper):
    @tooled
    def query(
        self,
        # Name of author to query (mutually exclusive with "author-id")
        # [alias: -a]
        # [nargs: +]
        author: Option = [],
        # ID of author to query (mutually exclusive with "author")
        author_id: Option & str = None,
        # Institution to query
        # [alias: -i]
        # [nargs: +]
        institution: Option = [],
        # Title of the paper (mutually exclusive with "exact-title")
        # [alias: -t]
        # [nargs: +]
        title: Option = [],
        # Exact title to query (mutually exclusive with "title")
        # [alias: -T]
        # [nargs: +]
        exact_title: Option = [],
        # If specified, display debug info
        verbose: Option & bool = False,
    ):
        # paperoni query openalex --option xyz --flag
        if isinstance(author, list):
            author = " ".join(author)
        if isinstance(institution, list):
            institution = " ".join(institution)
        if isinstance(title, list):
            title = " ".join(title)
        if isinstance(exact_title, list):
            exact_title = " ".join(exact_title)

        if verbose:
            print(f"{author=}")
            print(f"{author_id=}")
            print(f"{institution=}")
            print(f"{title=}")

        qm = OpenAlexQueryManager()
        filters = []

        if author and author_id:
            raise QueryError("Cannot query both author and author ID")
        elif author:
            if verbose:
                print("[search author]", author)
            author_id = qm.find_author_id(author)
            if author_id is None:
                if verbose:
                    print("[no author found]", author)
                return
        if author_id is not None:
            filters.append(f"author.id:{author_id}")

        if institution:
            if verbose:
                print("[query institution]", institution)
            institution_id = qm.find_institution_id(institution)
            if institution_id is None:
                if verbose:
                    print("[no institution found]", institution)
                    return
            filters.append(f"institutions.id:{institution_id}")

        if title and exact_title:
            raise QueryError("Cannot query both title and exact title")
        elif title:
            filters.append(f"display_name.search:{title}")
        elif exact_title:
            # No steam, and quotation mark around title, to try to get exact title
            # https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities#boolean-searches
            filters.append(f'display_name.search.no_stem:"{exact_title}"')

        params = {}
        if filters:
            params["filter"] = ",".join(filters)
            if verbose:
                print("[filters]", params["filter"])

        yield from qm.works(**params)

    @tooled
    def prepare(self):
        # paperoni prepare openalex
        return []

    @tooled
    def acquire(self):
        # paperoni acquire openalex
        return []


__scrapers__ = {"openalex": OpenAlexScraper}
