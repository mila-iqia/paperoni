import itertools
from unittest.mock import patch

import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.miniconf import ErrorPolicy, MiniConf, conference_urls
from paperoni.model import PaperInfo

from ..utils import check_papers, iter_affiliations


@pytest.mark.parametrize(
    ["conference", "query_params"],
    itertools.product(
        conference_urls, [{"affiliation": "mila"}, {"author": "Yoshua Bengio"}]
    ),
)
async def test_query(data_regression: DataRegressionFixture, conference, query_params):
    discoverer = MiniConf()

    papers: list[PaperInfo] = sorted(
        [
            p
            async for p in discoverer.query(
                conference, year=2024, **query_params, error_policy=ErrorPolicy.RAISE
            )
        ],
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


async def test_error_policy(capsys):
    discoverer = MiniConf()

    # patch MiniConf.convert_paper to raise an exception
    with patch.object(MiniConf, "convert_paper", side_effect=Exception):
        with pytest.raises(Exception):
            await anext(
                discoverer.query("neurips", year=2024, error_policy=ErrorPolicy.RAISE)
            )

        await anext(
            discoverer.query("neurips", year=2024, error_policy=ErrorPolicy.LOG),
            None,
        )

        out, _ = capsys.readouterr()
        assert "Error converting paper " in out
        # assert that there are at least a couple of exceptions
        assert len(out.split("Error converting paper ")) > 2
