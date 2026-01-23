from paperoni.discovery.pmlr import PMLR
from paperoni.model import Paper


async def test_query(dreg):
    discoverer = PMLR()

    assert "v180" in [v async for v in discoverer.list_volumes()], (
        "Could not find volume v180"
    )

    papers: list[Paper] = sorted(
        [p async for p in discoverer.query(volume="v180", name="Yoshua Bengio")],
        key=lambda x: x.title,
    )

    assert papers, "No papers found for Yoshua Bengio in v180"

    dreg(list[Paper], papers)
