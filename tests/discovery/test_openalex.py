import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.openalex import OpenAlex, OpenAlexQueryManager, QueryError

from ..utils import check_papers, iter_affiliations, split_on


@pytest.mark.parametrize(
    "query_params",
    [
        {"institution": "mila"},
        {"author": "Yoshua Bengio"},
        {"author_id": OpenAlexQueryManager().find_author_id("Yoshua Bengio")},
        {"title": "Hierarchical Latent Variable"},
    ],
)
def test_query(file_regression: FileRegressionFixture, query_params: dict[str, str]):
    discoverer = OpenAlex()

    papers: list[PaperInfo] = sorted(
        discoverer.query(
            **query_params,
            page=1,
            per_page=100,
            limit=1000,
        ),
        key=lambda x: x.paper.title,
    )

    assert papers, f"No papers found for {query_params=}"

    match next(iter(query_params.keys())):
        case "institution":
            assert all(
                [
                    aff
                    for aff in iter_affiliations(paper.paper)
                    if query_params["institution"].lower() in aff.name.lower()
                ]
                for paper in papers
            ), (
                f"Some papers do not contain the institution {query_params['institution']=}"
            )
        case "author":
            assert all(
                [
                    author
                    for author in paper.paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"Some papers do not contain the author {query_params['author']=}"
        case "author_id":
            assert [p.paper for p in papers] == [
                p.paper
                for p in sorted(
                    discoverer.query(
                        author="Yoshua Bengio", page=1, per_page=100, limit=100
                    ),
                    key=lambda x: x.paper.title,
                )
            ], (
                f"Querying by author ID should return the same papers as querying by author name"
            )
        case "title":
            # Search on title will return a match for each word in the query
            assert all(
                set(split_on(query_params["title"].lower()))
                & set(split_on(paper.paper.title.lower()))
                for paper in papers
            ), f"Some papers' titles do not contain the words {query_params['title']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)


@pytest.mark.parametrize(
    "query_params",
    [
        {
            "author": "Yoshua Bengio",
            "author_id": OpenAlexQueryManager().find_author_id("Yoshua Bengio"),
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
