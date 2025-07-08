from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.discovery.jmlr import JMLR

from ..utils import check_papers


def test_query(file_regression: FileRegressionFixture):
    discoverer = JMLR()

    assert "v24" in discoverer.list_volumes()

    papers: list[PaperInfo] = sorted(
        discoverer.query(volume="v24", name="Yoshua Bengio"),
        key=lambda x: x.paper.title,
    )

    assert papers, "No papers found for Yoshua Bengio in v24"

    check_papers(file_regression, papers)
