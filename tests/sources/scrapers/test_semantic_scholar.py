from pytest import fixture

from paperoni.sources.scrapers.semantic_scholar import SemanticScholarScraper
from .utils import Artifacts


@fixture(scope="module")
def artifacts():
    return Artifacts("semantic_scholar_artifacts")


@fixture
def scraper(config_empty):
    return SemanticScholarScraper(config_empty, config_empty.database)


def test_query_title(scraper, artifacts):
    assert artifacts["autodiff_query"].isin(
        scraper.query(title=["automatic differentiation in ml where we are"])
    )


def test_query_author(scraper, artifacts):
    assert artifacts["autodiff_query"].isin(
        scraper.query(author=["Olivier Breuleux"])
    )
