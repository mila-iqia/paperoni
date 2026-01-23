from paperoni.discovery.paperoni_v2 import PaperoniV2
from paperoni.model import Paper


async def test_query(dreg):
    discoverer = PaperoniV2()

    paper = await anext(discoverer.query())

    dreg(list[Paper], [paper])
