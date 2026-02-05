from typing import Literal

from ..config import config
from ..model import Link
from .fetch import register_fetch
from .formats import paper_from_jats


@register_fetch
async def pubmed(typ: Literal["pmc"], link: str):
    pmc_id = link
    soup = await config.fetch.read_retry(
        # PubMed Central OAI-PMH API : https://pmc.ncbi.nlm.nih.gov/tools/oai/
        f"https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm",
        format="xml",
    )
    return paper_from_jats(
        soup,
        links=[Link(type="pmc", link=pmc_id)],
    )
