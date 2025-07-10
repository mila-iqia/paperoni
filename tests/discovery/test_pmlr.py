from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.pmlr import PMLR

from ..utils import check_papers


def test_query(data_regression: DataRegressionFixture):
    discoverer = PMLR()

    assert "v180" in discoverer.list_volumes(), "Could not find volume v180"

    papers: list[PaperInfo] = sorted(
        discoverer.query(volume="v180", name="Yoshua Bengio"),
        key=lambda x: x.paper.title,
    )

    assert papers, "No papers found for Yoshua Bengio in v180"

    check_papers(data_regression, papers)
