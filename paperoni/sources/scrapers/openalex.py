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
from ...utils import QueryError, link_generators as LINK_GENERATORS

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


def _get_link(link_type: str, link_value: str) -> Link:
    if link_type == "pmid":
        link_type = "pubmed"
    if link_type in LINK_GENERATORS:
        # Extract relevant part.
        # Relevant part should be the part of `link_value` located in same place
        # as placeholder `{}` in `abstract` path model.
        # We assume model contains placeholder `{}` only once.
        abstract_path_model: str = LINK_GENERATORS[link_type]["abstract"]
        ref_start = abstract_path_model.index("{")
        nb_chars_after_ref = len(abstract_path_model) - (ref_start + 2)

        assert link_value[:ref_start] == abstract_path_model[:ref_start]

        relevant_part = link_value[
            ref_start : (
                -nb_chars_after_ref if nb_chars_after_ref else len(link_value)
            )
        ]
    else:
        # Keep full link
        relevant_part = link_value
    return Link(type=link_type, link=relevant_part)


class OpenAlexQueryManager:
    def __init__(self, *, mailto=None):
        self.conn = HTTPSAcquirer("api.openalex.org", format="json")
        self.mailto = mailto

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

    def _list(
        self,
        path: str,
        per_page: int = None,
        page: int = None,
        verbose=False,
        **params,
    ):
        pagination = page is not None and per_page is not None
        if page is None:
            page = 1
        if per_page is None:
            per_page = 25
        while True:
            local_params = {"page": page, "per-page": per_page, **params}
            results = self._evaluate(path, **local_params)
            if not results["results"]:
                # No more results.
                break
            if verbose:
                nb_results = len(results["results"])
                nb_total = results["meta"]["count"]
                nb_page = nb_total // per_page + bool(nb_total % per_page)
                print(
                    f"[page {page} / {nb_page}, {nb_results} results per page, {nb_total} total results]"
                )
            for entry in results["results"]:
                yield entry
            if pagination:
                # Display only this page
                break
            # Next page
            page += 1

    def _evaluate(self, path: str, **params):
        if self.mailto:
            params["mailto"] = self.mailto
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
        # Assert consistency in locations
        locations = data["locations"]
        if locations:
            assert locations[0] == data["primary_location"]
        else:
            assert data["primary_location"] is None
            assert data["best_oa_location"] is None

        # Assert consistency in paper ids
        if data.get("doi"):
            assert data["doi"] == data["ids"]["doi"]

        # NB: From locations we can collect links that directly lead to paper.
        # We collect them here so that they can also be added to paper "links" field.
        links_from_locations = []
        for location in locations:
            if location["landing_page_url"]:
                links_from_locations.append(
                    _get_link(
                        "url",
                        location["landing_page_url"],
                    )
                )
            if location["pdf_url"]:
                links_from_locations.append(
                    _get_link("pdf", location["pdf_url"])
                )

        # For releases, we will use only primary location
        release_locations = []
        if (
            data["primary_location"] is not None
            and data["primary_location"]["source"] is not None
        ):
            release_locations = [data["primary_location"]]

        # We will use work publication date with primary location to set release
        publication_date = datetime.fromisoformat(data["publication_date"])

        # We will save open access url in paper links
        oa_url = data["open_access"]["oa_url"]

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
                            _get_link("openalex", authorship["author"]["id"])
                        ]
                        + (
                            [
                                _get_link(
                                    "orcid",
                                    authorship["author"]["orcid"],
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
                        date=publication_date,
                        date_precision=DatePrecision.day,
                        volume=None,
                        publisher=location["source"]["host_organization_name"],
                        aliases=[],
                        links=(
                            [
                                _get_link(
                                    "url",
                                    location["landing_page_url"],
                                )
                            ]
                            if location["landing_page_url"]
                            else []
                        )
                        + (
                            [_get_link("pdf", location["pdf_url"])]
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
                for location in release_locations
            ],
            topics=[
                Topic(name=data_concept["display_name"])
                for data_concept in data["concepts"]
            ],
            links=[_get_link(typ, ref) for typ, ref in data["ids"].items()]
            + ([_get_link("open-access", oa_url)] if oa_url is not None else [])
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
        # Page of results to display (start at 1). Need argument "per_page". By default, all results are displayed.
        page: Option & int = None,
        # Number of results to display per page. Need argument "page". By default, all results are displayed.
        per_page: Option & int = None,
        # If specified, display debug info
        # [alias: -v]
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

        if verbose and self.config.mailto:
            print("[openalex: using polite pool]")
        qm = OpenAlexQueryManager(mailto=self.config.mailto)
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
            # No stemming, and quotation mark around title, to try to get exact title
            # https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities#boolean-searches
            filters.append(f'display_name.search.no_stem:"{exact_title}"')

        params = {}
        if filters:
            params["filter"] = ",".join(filters)
            if verbose:
                print("[filters]", params["filter"])
        if page is not None and per_page is not None:
            if page < 1:
                raise QueryError("page must be >= 1")
            if per_page < 1 or per_page > 200:
                raise QueryError("per_page must be >= 1 and <= 200")
            params["page"] = page
            params["per_page"] = per_page
        elif page is not None or per_page is not None:
            raise QueryError(
                "Need both page and per_page for pagination, or none of them to display all results"
            )

        yield from qm.works(**params, verbose=verbose)

    @tooled
    def prepare(self):
        # paperoni prepare openalex
        return []

    @tooled
    def acquire(self):
        # paperoni acquire openalex
        return []


__scrapers__ = {"openalex": OpenAlexScraper}
