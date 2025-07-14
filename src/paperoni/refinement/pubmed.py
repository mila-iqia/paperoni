from typing import Literal

from ovld import ovld

from ..acquire import readpage
from ..model import Link
from .fetch import fetch
from .formats import paper_from_jats


@ovld
def fetch(type: Literal["pmc"], link: str):
    pmc_id = link
    soup = readpage(
        f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmc_id}&metadataPrefix=pmc_fm",
        format="xml",
    )
    return paper_from_jats(
        soup,
        links=[Link(type="pmc", link=pmc_id)],
    )
