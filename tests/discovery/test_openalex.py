import json

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.openalex import OpenAlex, OpenAlexQueryManager, QueryError

from ..utils import iter_affiliations, sort_keys


@pytest.mark.parametrize(
    "query_params",
    [
        {"institution": "mila"},
        {"author": "Yoshua Bengio"},
        {"author_id": OpenAlexQueryManager().find_author_id("Yoshua Bengio")},
        {"title": "Hierarchical Latent Variable"},
        {
            "exact_title": "A Hierarchical Latent Variable Encoder-Decoder Model for Generating Dialogues"
        },
    ],
)
def test_query(file_regression: FileRegressionFixture, query_params: dict[str, str]):
    discoverer = OpenAlex()

    papers = sorted(
        discoverer.query(
            **query_params,
            page=1,
            per_page=100,
            limit=100,
        ),
        key=lambda x: x.title,
    )

    match next(iter(query_params.keys())):
        case "institution":
            assert all(
                [
                    aff
                    for aff in iter_affiliations(paper)
                    if query_params["institution"].lower() in aff.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['institution']=}"
        case "author":
            assert all(
                [
                    author
                    for author in paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['author']=}"
        case "author_id":
            assert papers == sorted(
                discoverer.query(
                    author="Yoshua Bengio", page=1, per_page=100, limit=100
                ),
                key=lambda x: x.title,
            ), f"Querying by author ID should return the same papers as querying by author name"
        case "title":
            assert all(
                [query_params["title"].lower() in paper.title.lower()]
                for paper in papers
            ), f"No paper found for {query_params['title']=}"
        case "exact_title":
            assert all(
                [query_params["exact_title"].lower() == paper.title.lower()]
                for paper in papers
            ), f"No paper found for {query_params['exact_title']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    # Using file_regression and json.dumps to avoid
    # yaml.representer.RepresenterError on DatePrecision
    file_regression.check(
        json.dumps(sort_keys(papers[:5]), indent=2), extension=".json"
    )


@pytest.mark.parametrize(
    "query_params",
    [
        {
            "author": "Yoshua Bengio",
            "author_id": OpenAlexQueryManager().find_author_id("Yoshua Bengio"),
        },
        {
            "title": "Hierarchical Latent Variable",
            "exact_title": "A Hierarchical Latent Variable Encoder-Decoder Model for Generating Dialogues",
        },
        {"page": 0, "per_page": 1},
        {"page": None, "per_page": 1},
        {"page": 1, "per_page": 0},
        {"page": 1, "per_page": 201},
        {"page": 1, "per_page": None},
    ],
)
def test_query_error(query_params):
    discoverer = OpenAlex()
    with pytest.raises(QueryError):
        next(discoverer.query(**query_params))
