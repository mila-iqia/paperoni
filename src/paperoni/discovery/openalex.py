import pprint
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from ..config import config
from ..model.classes import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
    Release,
    Topic,
    Venue,
    VenueType,
    rescore,
)
from ..model.focus import Focus, Focuses
from ..utils import QueryError, link_generators as LINK_GENERATORS, url_to_id
from .base import Discoverer

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

WORK_TYPES = {
    "article",
    "book-chapter",
    "dataset",
    "preprint",
    "dissertation",
    "book",
    "review",
    "paratext",
    "libguides",
    "letter",
    "other",
    "reference-entry",
    "report",
    "editorial",
    "peer-review",
    "erratum",
    "standard",
    "grant",
    "supplementary-materials",
    "retraction",
}

DEFAULT_WORK_TYPES = {
    "article",
    # "book-chapter",
    # "dataset",
    "preprint",
    # "dissertation",
    "book",
    # "review",
    # "paratext",
    # "libguides",
    # "letter",
    # "other",
    # "reference-entry",
    # "report",
    # "editorial",
    # "peer-review",
    # "erratum",
    # "standard",
    # "grant",
    # "supplementary-materials",
    # "retraction",
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
            ref_start : (-nb_chars_after_ref if nb_chars_after_ref else len(link_value))
        ]
    elif urlid := url_to_id(link_value):
        typ, lnk = urlid
        return Link(type=typ, link=lnk)
    else:
        # Keep full link
        relevant_part = link_value
    return Link(type=link_type, link=relevant_part)


class OpenAlexQueryManager:
    def __init__(self, *, mailto=None, work_types=DEFAULT_WORK_TYPES):
        self.mailto = mailto
        self.work_types = work_types

    def find_author_id(self, author: str) -> Optional[str]:
        found = self._evaluate("authors", filter=f"display_name.search:{author}")
        results = found["results"]
        return results[0]["id"] if results else None

    def find_institution_id(self, institution: str) -> Optional[str]:
        found = self._evaluate(
            "institutions", filter=f"display_name.search:{institution}"
        )
        results = found["results"]
        return results[0]["id"] if results else None

    def works(self, **params):
        for entry in self._list("works", **params):
            if result := self._try_wrapping_paper(entry):
                yield result

    def _list(
        self,
        path: str,
        per_page: int = None,
        page: int = None,
        limit: int = None,
        verbose=False,
        **params,
    ):
        n = 0
        pagination = page is not None and per_page is not None
        if page is None:
            page = 1
        if per_page is None:
            per_page = 100
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
                n += 1
                yield entry
                if limit and n >= limit:
                    return
            if pagination:
                # Display only this page
                break
            # Next page
            page += 1

    def _evaluate(self, path: str, **params):
        if self.mailto:
            params["mailto"] = self.mailto
        jdata = config.fetch.read_retry(
            f"https://api.openalex.org/{path}", params=params, format="json"
        )
        if jdata is None:
            raise QueryError("Received bad JSON")
        if "message" in jdata:
            if "error" in jdata:
                error_info = f"[error] {jdata['error']} [message] {jdata['message']}"
            else:
                error_info = jdata["message"]
            raise QueryError(error_info)
        assert "meta" in jdata
        assert "results" in jdata
        return jdata

    def _try_wrapping_paper(self, data: dict) -> PaperInfo:
        try:
            return self._wrap_paper(data)
        except Exception as exc:
            raise Exception(pprint.pformat(data)) from exc

    def _wrap_paper(self, data: dict) -> PaperInfo:
        # Assert consistency in locations
        typ = data["type"]
        if typ not in self.work_types:
            return None

        locations = data["locations"]

        ## These asserts start failing in the v2 of the data version
        # if locations:
        #     assert locations[0] == data["primary_location"]
        # else:
        #     assert data["primary_location"] is None
        #     assert data["best_oa_location"] is None

        # # Assert consistency in paper ids
        # if data.get("doi"):
        #     assert data["doi"] == data["ids"]["doi"]

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
                links_from_locations.append(_get_link("pdf", location["pdf_url"]))

        def venue_name(loc):
            vn = candidate.get("raw_source_name", None)
            if vn is None and loc["source"]:
                vn = loc["source"]["display_name"]
            if vn and vn.startswith("http"):
                return None
            return vn

        # For releases, we will use only primary location if there is a source name
        release_locations = []
        candidates = [data["primary_location"], *locations]
        for candidate in candidates:
            if candidate is not None and venue_name(candidate) is not None:
                release_locations = [candidate]
                break

        # We will use work publication date with primary location to set release
        publication_date = date.fromisoformat(data["publication_date"])

        # We will save open access url in paper links
        oa_url = data["open_access"]["oa_url"]

        links = {_get_link(typ, ref) for typ, ref in data["ids"].items()}
        links.update([_get_link("open-access", oa_url)] if oa_url is not None else [])
        links.update(links_from_locations)
        links = list(links)
        links.sort(key=lambda l: (l.type, l.link))

        paper = Paper(
            title=data["display_name"] or "Untitled",
            abstract=self._reconstruct_abstract(data["abstract_inverted_index"] or {}),
            authors=[
                PaperAuthor(
                    display_name=authorship["author"]["display_name"],
                    author=Author(
                        name=authorship["author"]["display_name"],
                        aliases=[],
                        links=[_get_link("openalex", authorship["author"]["id"])]
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
                            category=INSTITUTION_CATEGORY_MAPPING.get(
                                author_inst["type"], InstitutionCategory.unknown
                            ),
                            aliases=[],
                        )
                        for author_inst in authorship["institutions"]
                        if author_inst["display_name"]
                    ],
                )
                for authorship in data["authorships"]
            ],
            releases=[
                Release(
                    venue=Venue(
                        type=VENUE_TYPE_MAPPING[
                            (lsrc := location["source"] or {}).get("type", "repository")
                        ],
                        name=venue_name(location),
                        series="",
                        date=publication_date,
                        date_precision=DatePrecision.day,
                        volume=None,
                        publisher=lsrc.get("host_organization_name", None),
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
                            location.get("version", None)
                            in ("acceptedVersion", "publishedVersion")
                        ),
                    ),
                    status=(
                        "published"
                        if location.get("is_published")
                        else (
                            "accepted"
                            if location.get("is_accepted")
                            else ("preprint" if typ == "preprint" else "unknown")
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
            links=links,
        )

        # Create unique key based on OpenAlex work ID
        # OpenAlex IDs are in the format "https://openalex.org/W2741809807"
        openalex_id = data["id"].split("/")[-1]
        paper_key = f"openalex:{openalex_id}"

        return PaperInfo(
            key=paper_key,
            acquired=datetime.now(),
            paper=paper,
            info={"discovered_by": {"openalex": openalex_id}},
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


@dataclass
class OpenAlex(Discoverer):
    # Email associated with the query, for politeness
    mailto: str = field(default_factory=lambda: config.mailto)

    def query(
        self,
        # Name of author to query (mutually exclusive with "author-id")
        # [alias: -a]
        author: str = None,
        # ID of author to query (mutually exclusive with "author")
        author_id: str = None,
        # Institution to query
        # [alias: -i]
        institution: str = None,
        # Title of the paper (mutually exclusive with "exact-title")
        # [alias: -t]
        title: str = None,
        # Page of results to display (start at 1). Need argument "per_page". By default, all results are displayed.
        page: int = None,
        # Number of results to display per page. Need argument "page". By default, all results are displayed.
        per_page: int = None,
        # Max number of papers to show
        limit: int = None,
        # Work types
        work_types: list[str] = DEFAULT_WORK_TYPES,
        # If specified, display debug info
        # [alias: -v]
        verbose: bool = False,
        # Data version
        data_version: Literal["1", "2"] = "1",
        # A list of focuses
        focuses: Focuses = None,
    ):
        """Query OpenAlex for works."""
        if focuses:
            if limit is not None:
                print(
                    "The 'limit' parameter is ignored when 'focuses' are provided.",
                    file=sys.stderr,
                )
            if any((page is not None, per_page is not None)):
                print(
                    "The 'page' and 'per_page' parameters will effectively be multiplied by the number of 'focuses' provided.",
                    file=sys.stderr,
                )

            for focus in focuses.focuses:
                match focus:
                    case Focus(drive_discovery=False):
                        continue
                    case Focus(type="author", name=name, score=score):
                        yield from rescore(
                            self.query(
                                author=name,
                                institution=institution,
                                title=title,
                                data_version=data_version,
                                page=page,
                                per_page=per_page,
                                verbose=verbose,
                                work_types=work_types,
                            ),
                            score,
                        )
                    case Focus(type="author_openalex", name=aid, score=score):
                        yield from rescore(
                            self.query(
                                author_id=aid,
                                institution=institution,
                                title=title,
                                data_version=data_version,
                                page=page,
                                per_page=per_page,
                                verbose=verbose,
                                work_types=work_types,
                            ),
                            score,
                        )
                    case Focus(type="institution", name=name, score=score):
                        yield from rescore(
                            self.query(
                                author=author,
                                institution=name,
                                title=title,
                                data_version=data_version,
                                page=page,
                                per_page=per_page,
                                verbose=verbose,
                                work_types=work_types,
                            ),
                            score,
                        )
            return

        if verbose and self.mailto:
            print("[openalex: using polite pool]")
        qm = OpenAlexQueryManager(mailto=self.mailto, work_types=work_types)
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

        if title:
            filters.append(f"display_name.search:{title}")

        params = {"data_version": str(data_version)}
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

        yield from qm.works(**params, limit=limit, verbose=verbose)
