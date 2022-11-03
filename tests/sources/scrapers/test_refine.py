import pytest
from pytest import fixture

from paperoni.display import display
from paperoni.sources.scrapers.refine import Refiner


@fixture
def scraper(config_refine):
    scraper = Refiner(config_refine, config_refine.database)
    with scraper.db:
        yield scraper


links_for_tests = [
    "doi:10.1101/2022.05.12.491149",
    "doi:10.1109/icassp43922.2022.9746434",
    "doi:10.1016/j.ins.2022.04.032",
    "arxiv:2102.08501",
    "arxiv:2108.01005",
]


@pytest.mark.parametrize(
    argnames=["lnk"], argvalues=[[x] for x in links_for_tests]
)
def test_query(lnk, scraper, data_regression):
    result, = scraper.query(link=lnk)
    display(result)
    data_regression.check(result.tagged_dict())
