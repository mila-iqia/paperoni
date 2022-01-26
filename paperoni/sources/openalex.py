import json
import requests
import pprint

from ..papers2 import Author, Link, Paper, Release, Topic, Venue
from ..query import QueryError, reconstruct_abstract
from ..sql.collection import MutuallyExclusiveError


class OpenAlexQueryManager:
    def _evaluate(self, path: str, **params):
        # NB: I got server internal error (code 500) when using HTTPSConnection, and I don't know why,
        # but using module `requests` works finely.
        r = requests.get(f"https://api.openalex.org/{path}", params=params)
        jdata = json.loads(r.text)
        if "error" in jdata:
            raise QueryError(jdata)
        return jdata

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

    def _wrap_paper(self, data: dict) -> Paper:
        return Paper(
            links=[Link(type=typ, ref=ref) for typ, ref in data["ids"].items()]
            + [Link(type="doi", ref=data["doi"])],
            title=data["display_name"],
            abstract=reconstruct_abstract(
                data["abstract_inverted_index"] or {}
            ),
            authors=[
                Author(
                    links=[
                        Link(type="openalex", ref=data_author["author"]["id"]),
                        Link(type="orcid", ref=data_author["author"]["orcid"]),
                    ],
                    name=data_author["author"]["display_name"],
                    aliases=(),
                    affiliations=[
                        data_institution["display_name"]
                        for data_institution in data_author["institutions"]
                    ],
                )
                for data_author in data["authorships"]
            ],
            releases=[
                Release(
                    venue=Venue(
                        longname=data["host_venue"]["display_name"],
                        type=data["host_venue"]["type"],
                    ),
                    date=data["publication_date"],
                    year=data["publication_year"],
                )
            ]
            + [
                Release(
                    venue=Venue(
                        longname=data_host["display_name"],
                        type=data_host.get("type", None),
                    ),
                )
                for data_host in data["alternate_host_venues"]
            ],
            topics=[
                Topic(name=data_concept["display_name"])
                for data_concept in data["concepts"]
            ],
            citation_count=data["cited_by_count"],
        )

    def get_paper(self, paper_id: str):
        return self._wrap_paper(self._evaluate(f"works/{paper_id}"))

    def find_papers(
        self,
        *,
        author,
        venue,
        institution,
        concept,
        title,
        words,
        year,
        start,
        end,
        recent,
        cited,
        per_page=25,
        page=1,
        verbose=False,
    ):
        filters = []
        params = {}
        # For author, venue, institution and concept (keyword), filter need entity IDs.
        # So, we must find a corresponding ID from user given entity name.
        # OpenAlex may return many results for a search, so we just take 1st found entry
        # to get an ID.
        if author is not None:
            if verbose:
                print("[search author]", author)
            found_author = self._evaluate(
                "authors", filter=f"display_name.search:{author}"
            )
            results = found_author["results"]
            if not results:
                raise RuntimeError(f"No author found: {author}")
            filters.append(f"author.id:{results[0]['id']}")
        if venue is not None:
            if verbose:
                print("[search venue]", venue)
            found_venue = self._evaluate(
                "venues", filter=f"display_name.search:{venue}"
            )
            results = found_venue["results"]
            if not results:
                raise RuntimeError(f"No venue found: {venue}")
            filters.append(f"host_venue.id:{results[0]['id']}")
        if institution is not None:
            if verbose:
                print("[search institution]", institution)
            found_institution = self._evaluate(
                "institutions", filter=f"display_name.search:{institution}"
            )
            results = found_institution["results"]
            if not results:
                raise RuntimeError(f"No institution found: {institution}")
            filters.append(f"institutions.id:{results[0]['id']}")
        if concept is not None:
            if verbose:
                print("[search concept]", concept)
            found_concept = self._evaluate(
                "concepts", filter=f"display_name.search:{concept}"
            )
            results = found_concept["results"]
            if not results:
                raise RuntimeError(f"No concept found: {concept}")
            filters.append(f"concepts.id:{results[0]['id']}")

        if title and words:
            raise MutuallyExclusiveError("title", "words")
        elif title:
            filters.append(f'display_name.search:"{title}"')
        elif words:
            filters.append(f"display_name.search:{'+'.join(words)}")
        # OpenAlex does not seems to allow multiple filtering for a same parameter,
        # ie. `publication_date:>something,publication_date:<something` seems to
        # take only the last one `publication_date:<something`.
        if (start is not None) + (end is not None) + (year is not None) > 1:
            raise MutuallyExclusiveError("year", "start", "end")
        if start is not None:
            filters.append(f"publication_date:>{start}")
        elif end is not None:
            filters.append(f"publication_date:<{end}")
        elif year is not None:
            filters.append(f"publication_year:{year}")

        if filters:
            params["filter"] = ",".join(filters)

        if recent and cited:
            raise MutuallyExclusiveError("recent", "cited")
        elif recent:
            params["sort"] = "publication_date:desc"
        elif cited:
            params["sort"] = "cited_by_count:desc"

        params["per-page"] = per_page
        params["page"] = page
        if verbose:
            print("[parameters]")
            for key, value in params.items():
                print(f"{key}:", value)
        for i, result in enumerate(self._list("works", **params)):
            try:
                if verbose:
                    print(f"[paper {i + 1}]")
                yield self._wrap_paper(result)
            except Exception as exc:
                raise Exception(pprint.pformat(result)) from exc
