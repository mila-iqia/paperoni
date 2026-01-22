from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest
from pytest_regressions.data_regression import DataRegressionFixture
from serieux import deserialize, serialize

from paperoni.model.classes import PaperInfo
from paperoni.refinement.fetch import fetch_all
from paperoni.refinement.llm_normalize import normalize_paper
from tests.utils import check_papers


@pytest.fixture(scope="module")
async def paper_info():
    # Prepared with:
    # paperoni refine --link "openreview:_3FyT_W1DW" --tags pdf --norm
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
                    [p async for p in fetch_all([("openreview", "_3FyT_W1DW")], tags={})],
                ),
                None,
            )
            is None
        )

        yield next(
            filter(
                lambda pinfo: "pdf" in pinfo.info["refined_by"],
                [
                    p
                    async for p in fetch_all([("openreview", "_3FyT_W1DW")], tags={"pdf"})
                ],
            )
        )


def test_pdf(data_regression: DataRegressionFixture, paper_info: PaperInfo):
    assert paper_info is not None

    check_papers(data_regression, [paper_info])


def test_pdf_norm(data_regression: DataRegressionFixture, paper_info: PaperInfo):
    assert paper_info is not None

    # Copy the paper_info to avoid modifying the original object
    paper_info = deserialize(PaperInfo, serialize(PaperInfo, paper_info))

    with patch(
        "paperoni.prompt.paperazzi_make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        normalized_paper = normalize_paper(paper_info.paper)

    paper_info.paper = normalized_paper
    check_papers(data_regression, [paper_info])
