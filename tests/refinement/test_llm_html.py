from pathlib import Path
from unittest.mock import patch

import gifnoc
import pytest
from serieux import deserialize, serialize

from paperoni.model.classes import Paper
from paperoni.refinement.fetch import fetch_all
from paperoni.refinement.llm_normalize import normalize_paper


@pytest.fixture(scope="module")
async def paper_info():
    # Prepared with:
    # paperoni refine --link "doi:10.1038/s41597-023-02214-y" --tags html --norm author --norm institution --norm venue
    with (
        gifnoc.overlay({"paperoni.data_path": str(Path(__file__).parent / "data")}),
        patch(
            "paperoni.prompt.paperazzi_make_key",
            lambda *args, **kwargs: "DUMMY_KEY",
        ),
    ):
        assert (
            next(
                filter(
                    lambda pinfo: "html" in pinfo.info["refined_by"],
                    [
                        p
                        async for p in fetch_all(
                            [("doi", "10.1038/s41597-023-02214-y")], tags={}
                        )
                    ],
                ),
                None,
            )
            is None
        )

        yield next(
            filter(
                lambda pinfo: "html" in pinfo.info["refined_by"],
                [
                    p
                    async for p in fetch_all(
                        [("doi", "10.1038/s41597-023-02214-y")], tags={"html"}
                    )
                ],
            )
        )


def test_html(dreg, paper_info: Paper):
    assert paper_info is not None

    dreg(list[Paper], [paper_info])


def test_html_norm(dreg, paper_info: Paper):
    assert paper_info is not None

    # Copy the paper_info to avoid modifying the original object
    paper_info = deserialize(Paper, serialize(Paper, paper_info))

    with patch(
        "paperoni.prompt.paperazzi_make_key",
        lambda *args, **kwargs: "DUMMY_KEY",
    ):
        paper_info = normalize_paper(paper_info)

    dreg(list[Paper], [paper_info])
