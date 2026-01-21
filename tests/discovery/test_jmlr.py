
from paperoni.discovery.jmlr import JMLR
from paperoni.model import PaperInfo


async def test_query(dreg):
    discoverer = JMLR()

    assert "v24" in [v async for v in discoverer.list_volumes()], (
        "Could not find volume v24"
    )

    papers: list[PaperInfo] = sorted(
        [p async for p in discoverer.query(volume="v24", name="Yoshua Bengio")],
        key=lambda x: x.paper.title,
    )

    assert papers, "No papers found for Yoshua Bengio in v24"

    dreg(list[PaperInfo], papers)
