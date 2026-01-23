from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest

from paperoni.model.classes import Paper
from paperoni.refinement.fetch import fetch_all
from paperoni.refinement.llm_normalize import normalize_paper


@pytest.fixture(scope="module")
async def paper_info():
    # Prepared with:
    # paperoni refine --link "doi:10.1109/cvpr52733.2024.01307" --norm
    with gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}):
        yield await anext(fetch_all([("doi", "10.1109/cvpr52733.2024.01307")], tags={}))


def test_norm(dreg, paper_info: Paper):
    assert paper_info is not None

    with patch(
        "paperoni.prompt.paperazzi_make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        paper_info = normalize_paper(paper_info)

    dreg(list[Paper], [paper_info])
