import itertools

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.miniconf import MiniConf, conference_urls

from ..utils import check_papers, iter_affiliations


@pytest.mark.parametrize(
    ["conference", "query_params"],
    itertools.product(
        conference_urls, [{"affiliation": "mila"}, {"author": "Yoshua Bengio"}]
    ),
)
def test_query(file_regression: FileRegressionFixture, conference, query_params):
    discoverer = MiniConf()

    papers: list[PaperInfo] = sorted(
        discoverer.query(conference, year=2024, **query_params),
        key=lambda x: x.paper.title,
    )

    match next(iter(query_params.keys())):
        case "affiliation":
            assert all(
                [
                    aff
                    for aff in iter_affiliations(paper.paper)
                    if query_params["affiliation"].lower() in aff.name.lower()
                ]
                for paper in papers
            ), f"Some papers do not contain the affiliation {query_params['affiliation']=}"
        case "author":
            assert all(
                [
                    author
                    for author in paper.paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"Some papers do not contain the author {query_params['author']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)
