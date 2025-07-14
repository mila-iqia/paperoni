from typing import Literal

from ..acquire import readpage
from ..model import Link
from .fetch import register_fetch
from .formats import paper_from_jats


@register_fetch
def pubmed(type: Literal["pmc"], link: str):
    pmc_id = link
    soup = readpage(
        f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm",
        format="xml",
    )
    return paper_from_jats(
        soup,
        links=[Link(type="pmc", link=pmc_id)],
    )
