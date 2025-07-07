import itertools
from pathlib import Path

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.miniconf import MiniConf, conference_urls

from ..utils import check_papers, iter_affiliations


@pytest.fixture(autouse=True)
def cache_dir(tmpdir):
    _cache_dir = Path(tmpdir).parent.parent
    discoverer = MiniConf()

    for conference in conference_urls:
        next(discoverer.query(conference, year=2024, cache=_cache_dir))

    yield _cache_dir


@pytest.mark.parametrize(
    ["conference", "query_params"],
    itertools.product(
        conference_urls, [{"affiliation": "mila"}, {"author": "Yoshua Bengio"}]
    ),
)
def test_query(
    cache_dir, file_regression: FileRegressionFixture, conference, query_params
):
    discoverer = MiniConf()

    papers = sorted(
        discoverer.query(conference, year=2024, cache=cache_dir, **query_params),
        key=lambda x: x.title,
    )

    match next(iter(query_params.keys())):
        case "affiliation":
            assert all(
                [
                    aff
                    for aff in iter_affiliations(paper)
                    if query_params["affiliation"].lower() in aff.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['affiliation']=}"
        case "author":
            assert all(
                [
                    author
                    for author in paper.authors
                    if query_params["author"].lower() in author.author.name.lower()
                ]
                for paper in papers
            ), f"No paper found for {query_params['author']=}"
        case _:
            assert False, f"Unknown query parameter: {query_params=}"

    check_papers(file_regression, papers)
