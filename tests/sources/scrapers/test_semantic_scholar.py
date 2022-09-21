import json
from pathlib import Path

from pytest import fixture

from paperoni.sources.scrapers.semantic_scholar import SemanticScholarScraper


@fixture(scope="module")
def artifacts():
    return json.load(
        open(Path(__file__).parent / "semantic_scholar_artifacts.json")
    )


def test_query(config, database, artifacts):
    ss = SemanticScholarScraper(config, database)
    for entry in ss.query(
        title=["automatic differentiation in ml where we are"]
    ):
        assert json.loads(entry.tagged_json()) == artifacts["autodiff_query"]
        break
