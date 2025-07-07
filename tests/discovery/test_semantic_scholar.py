import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import Paper

from ..utils import check_papers, split_on


@pytest.mark.parametrize(
    "query_params",
    [
        # TODO: Fix this test. Querying by author returns unrelated papers.
        # {"author": "Yoshua Bengio"},
        # TODO: Fix this test. Querying by title returns unrelated papers.
        # {
        #     "title": "Hierarchical Latent Variable",
        # },
    ],
)
def test_query(file_regression: FileRegressionFixture, query_params: dict[str, str]):
    discoverer = SemanticScholar()

    papers = sorted(
        discoverer.query(**query_params, block_size=100, limit=1000),
        key=lambda x: x.title,
    )

    assert papers, f"No papers found for {query_params=}"

    match next(iter(query_params.keys())):
        case "author":
            assert all(
                [
                    author
                    for author in paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['author']=}"
        case "title":
            # Search on title will return a match for each word in the query
            assert all(
                set(split_on(query_params["title"].lower()))
                & set(split_on(paper.title.lower()))
                for paper in papers
            ), f"No paper found for {query_params['title']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)
