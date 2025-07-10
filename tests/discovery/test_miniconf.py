import itertools

import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.miniconf import MiniConf, conference_urls
from paperoni.model import PaperInfo

from ..utils import check_papers, iter_affiliations


@pytest.mark.parametrize(
    ["conference", "query_params"],
    itertools.product(
        conference_urls, [{"affiliation": "mila"}, {"author": "Yoshua Bengio"}]
    ),
)
def test_query(data_regression: DataRegressionFixture, conference, query_params):
    discoverer = MiniConf()

    papers: list[PaperInfo] = sorted(
        discoverer.query(conference, year=2024, **query_params),
        key=lambda x: x.paper.title,
    )

    match_found = False

    for param in query_params:
        match param:
            case "affiliation":
                assert all(
                    any(
                        query_params["affiliation"].lower() in aff.name.lower()
                        for aff in iter_affiliations(paper.paper)
                    )
                    for paper in papers
                ), (
                    f"Some papers do not contain the affiliation {query_params['affiliation']=}"
                )
                match_found = True

            case "author":
                assert all(
                    any(
                        query_params["author"].lower() in author.author.name.lower()
                        for author in paper.paper.authors
                    )
                    for paper in papers
                ), f"Some papers do not contain the author {query_params['author']=}"
                match_found = True

    if not match_found:
        assert False, f"Unknown query parameters: {query_params=}"

    check_papers(data_regression, papers)
