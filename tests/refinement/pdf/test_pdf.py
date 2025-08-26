from pathlib import Path
from unittest.mock import patch

from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.refinement.pdf import fetch_all
from tests.utils import check_papers


def test_analyse_pdf(data_regression: DataRegressionFixture):
    with (
        patch("paperoni.config.config.data_path", Path(__file__).parent / "data"),
        patch(
            "paperoni.refinement.pdf.pdf._make_key", lambda *args, **kwargs: "DUMMY_KEY"
        ),
    ):
        pinfo = next(fetch_all("openreview", "_3FyT_W1DW"))

    assert pinfo is not None

    check_papers(data_regression, [pinfo])
