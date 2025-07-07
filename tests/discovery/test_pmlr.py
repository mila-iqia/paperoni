from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.pmlr import PMLR

from ..utils import check_papers


def test_query(file_regression: FileRegressionFixture):
    discoverer = PMLR()

    assert "v180" in discoverer.list_volumes(), "Could not find volume v180"

    papers = sorted(
        discoverer.query(volume="v180", name="Yoshua Bengio"),
        key=lambda x: x.title,
    )

    check_papers(file_regression, papers)
