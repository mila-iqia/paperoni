from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest

from paperoni.__main__ import Work
from paperoni.model import Venue
from paperoni.model.classes import Paper
from paperoni.refinement.fetch import fetch_all
from paperoni.refinement.llm_normalize import norm_venue_prompt, normalize_paper


@pytest.fixture(scope="module")
async def paper_info():
    # Prepared with:
    # paperoni refine --link "doi:10.1109/cvpr52733.2024.01307" --norm author --norm institution --norm venue
    with gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}):
        yield await anext(fetch_all([("doi", "10.1109/cvpr52733.2024.01307")], tags={}))


@pytest.fixture(scope="module")
async def norm_paper_info():
    # Prepared with:
    # paperoni work --work-file tests/refinement/data/work_norm.yaml normalize
    with gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}):
        yield (
            Work(
                command=None,
                work_file=Path(__file__).parent / "data" / "work_norm.yaml",
            )
            .top.entries[0]
            .value.current
        )


def test_norm(dreg, paper_info: Paper):
    assert paper_info is not None

    with patch(
        "paperoni.prompt.paperazzi_make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        paper_info = normalize_paper(paper_info)

    dreg(list[Paper], [paper_info])


def test_norm_venue(dreg, norm_paper_info: Paper):
    venue = norm_paper_info.releases[0].venue

    with patch(
        "paperoni.prompt.paperazzi_make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        venue = norm_venue_prompt(venue)

    dreg(Venue, venue)
