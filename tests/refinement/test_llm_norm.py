from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from paperoni.model.classes import PaperInfo
from paperoni.refinement.fetch import fetch_all
from paperoni.refinement.llm_normalize import normalize_paper
from tests.utils import check_papers


@pytest.fixture(scope="module")
def paper_info():
    # Prepared with:
    # paperoni refine --link "doi:10.1109/cvpr52733.2024.01307" --norm
    with (
        gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}),
    ):
        yield next(fetch_all([("doi", "10.1109/cvpr52733.2024.01307")], tags={}))


def test_norm(data_regression: DataRegressionFixture, paper_info: PaperInfo):
    assert paper_info is not None

    with patch(
        "paperoni.refinement.llm_normalize.config.refine.prompt._make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        normalized_paper = normalize_paper(paper_info.paper)

    paper_info.paper = normalized_paper
    check_papers(data_regression, [paper_info])
