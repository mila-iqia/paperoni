from pathlib import Path
from unittest.mock import patch

import gifnoc
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.refinement.fetch import fetch_all
from tests.utils import check_papers


def test_pdf(data_regression: DataRegressionFixture):
    with (
        gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}),
        patch(
            "paperoni.refinement.llm_pdf._make_key", lambda *args, **kwargs: "DUMMY_KEY"
        ),
    ):
        assert (
            next(
                filter(
                    lambda pinfo: "pdf" in pinfo.info["refined_by"],
                    fetch_all("openreview", "_3FyT_W1DW", tags={}),
                ),
                None,
            )
            is None
        )

        pinfo = next(
            filter(
                lambda pinfo: "pdf" in pinfo.info["refined_by"],
                fetch_all("openreview", "_3FyT_W1DW", tags={"pdf"}),
            )
        )

    assert pinfo is not None

    check_papers(data_regression, [pinfo])
