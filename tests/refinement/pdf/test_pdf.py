from pathlib import Path
from unittest.mock import patch

from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.model.classes import PaperInfo
from paperoni.refinement.fetch import fetch_all
from tests.utils import check_papers


def test_analyse_pdf(data_regression: DataRegressionFixture):
    def _check_pdf(pinfo: PaperInfo):
        return "pdf" in [k.split(":")[0] for k in pinfo.info["refined_by"]]

    with (
        patch("paperoni.config.config.data_path", Path(__file__).parent / "data"),
        patch(
            "paperoni.refinement.pdf.pdf._make_key", lambda *args, **kwargs: "DUMMY_KEY"
        ),
    ):
        assert (
            next(
                filter(_check_pdf, fetch_all("openreview", "_3FyT_W1DW", tags={})),
                None,
            )
            is None
        )

        pinfo = next(
            filter(
                _check_pdf,
                fetch_all("openreview", "_3FyT_W1DW", tags={"prompt", "pdf"}),
            )
        )

    assert pinfo is not None

    check_papers(data_regression, [pinfo])
