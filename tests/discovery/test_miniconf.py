import itertools
import json
from pathlib import Path
from typing import Generator

import pytest
from serieux import serialize

from paperoni.discovery.miniconf import MiniConf, conference_urls
from paperoni.model.classes import Institution, Paper

from ..utils import sort_keys


def _iter_affiliations(paper: Paper) -> Generator[Institution, None, None]:
    for author in paper.authors:
        for affiliation in author.affiliations:
            yield affiliation


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
def test_query(cache_dir, data_regression, conference, query_params):
    discoverer = MiniConf()

    papers = sorted(
        discoverer.query(conference, year=2024, cache=cache_dir, **query_params),
        key=lambda x: x.title,
    )

    match query_params:
        case "affiliation":
            assert all(
                [
                    aff
                    for aff in _iter_affiliations(paper)
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

    data_regression.check(sort_keys(serialize(list[Paper], papers[:5])))
