from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest

from paperoni.discovery.scrape import Scrape
from paperoni.model import PaperInfo


@pytest.fixture(scope="session", autouse=True)
def touch_cache():
    for _f in (Path(__file__).parent / "data" / "html").glob("**/content.html"):
        _f.touch()


async def test_query(dreg):
    discoverer = Scrape()

    with (
        gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}),
        patch(
            "paperoni.prompt.paperazzi_make_key",
            lambda *args, **kwargs: "DUMMY_KEY",
        ),
    ):
        # Prepared with:
        # paperoni discover scrape --links "https://dadelani.github.io/publications"
        paper = await anext(discoverer.query())

    dreg(list[PaperInfo], [paper])
