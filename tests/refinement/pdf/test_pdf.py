from pathlib import Path
from unittest.mock import patch

from pytest_regressions.data_regression import DataRegressionFixture
from serieux import serialize

from paperoni.refinement.pdf.pdf import analyse_pdf


def test_analyse_pdf(data_regression: DataRegressionFixture):
    with patch("paperoni.config.config.data_path", Path(__file__).parent / "data"):
        pinfo = analyse_pdf("openreview", "_3FyT_W1DW")

    assert pinfo is not None

    data_regression.check(serialize(type(pinfo), pinfo))
