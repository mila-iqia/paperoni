import pytest
import requests

from paperoni.refinement.dblp import dblp
from paperoni.refinement.doi import crossref, datacite, unpaywall
from paperoni.refinement.fetch import _test_tags
from paperoni.refinement.title import arxiv_title, crossref_title, openalex_title


@pytest.mark.parametrize(
    ["f_tags", "tags", "pass_"],
    [
        (set(), set(), True),
        (set(), {"all"}, True),
        (set(), {"a"}, False),
        ({"a", "b"}, {"all"}, True),
        ({"a", "b"}, {"a"}, True),
        ({"a", "b"}, {"b"}, True),
        ({"a", "b"}, {"a", "b"}, True),
        ({"a", "b"}, {"a", "b", "c"}, False),
        ({"a", "b"}, {"a", "c"}, False),
        ({"a", "b"}, {"a", "c", "all"}, True),
        ({"a", "b", "c"}, {"a", "b", "c", "all"}, True),
    ],
)
def test__test_tags(f_tags, tags, pass_):
    assert _test_tags(f_tags, tags) == pass_


links = [
    # Crossref
    (crossref, "doi:10.1002/mp.17782"),
    (crossref, "doi:10.1007/s41109-021-00378-3"),
    (crossref, "doi:10.1007/978-3-032-07502-4_10"),
    (crossref, "doi:10.1016/j.jhin.2019.05.004"),
    (crossref, "doi:10.1016/j.jval.2024.03.2070"),
    (crossref, "doi:10.1016/j.neucom.2022.09.031"),
    (crossref, "doi:10.1109/comst.2024.3450292"),
    (crossref, "doi:10.1109/icassp43922.2022.9746662"),
    (crossref, "doi:10.1109/ICMLC63072.2024.10935257"),
    (crossref, "doi:10.7554/eLife.79919"),
    # Unpaywall
    (unpaywall, "doi:10.1002/mp.17782"),
    (unpaywall, "doi:10.1007/s41109-021-00378-3"),
    (unpaywall, "doi:10.1016/j.jhin.2019.05.004"),
    (unpaywall, "doi:10.1126/sciadv.abj1812"),
    (unpaywall, "doi:10.7554/eLife.79919"),
    (unpaywall, "doi:10.14569/ijacsa.2024.0150305"),
    # Datacite
    (datacite, "doi:10.48550/arXiv.2206.08164"),
    (datacite, "doi:10.48550/arXiv.2308.03977"),
    (datacite, "doi:10.48550/arXiv.2310.07819"),
    (datacite, "doi:10.48550/arXiv.2312.14279"),
    (datacite, "doi:10.48550/arXiv.2406.11919"),
    (datacite, "doi:10.48550/arXiv.2407.12161"),
    (datacite, "doi:10.48550/arXiv.2409.12917"),
    (datacite, "doi:10.48550/arXiv.2502.00561"),
    (datacite, "doi:10.48550/arXiv.2506.01225"),
    (datacite, "doi:10.48550/arXiv.2406.06946"),
    (datacite, "doi:10.48550/arXiv.2312.12604"),
    # # BiorXiv
    # TODO: fix timeout
    # (biorxiv, "doi:10.1101/2020.10.29.359778"),
    # (biorxiv, "doi:10.1101/2023.05.17.541168"),
    # (biorxiv, "doi:10.1101/2023.10.27.564468"),
    # (biorxiv, "doi:10.1101/2024.02.13.580150"),
    # (biorxiv, "doi:10.1101/2024.12.02.626449"),
    # (biorxiv, "doi:10.1101/2025.06.23.661173"),
    # (biorxiv, "doi:10.1101/2023.08.30.23294850"),
    # DBLP
    (dblp, "dblp:conf/icml/LachapelleDMMBL23"),
    (dblp, "dblp:conf/wacv/DaultaniL24"),
    (dblp, "dblp:conf/nips/LacosteLRSKLIDA23"),
    (dblp, "dblp:conf/icse-chase/AryaGR25"),
    (dblp, "dblp:conf/aaai/Rezaei-Shoshtari23"),
    # # Pubmed Central
    # TODO: fix timeout
    # (pubmed, "pmc:8900797"),
    # (pubmed, "pmc:11551764"),
    # (pubmed, "pmc:12136731"),
    # (pubmed, "pmc:11971501"),
    # (pubmed, "pmc:10684502"),
    # OpenAlex, by title
    (openalex_title, "title:Attention Is All You Need"),
    (
        openalex_title,
        "title:GraphMix: Improved Training of GNNs for Semi-Supervised Learning",
    ),
    # TODO: why do they not have this paper?
    # (
    #     openalex_title,
    #     "title:BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
    # ),
    # Crossref, by title
    (
        crossref_title,
        "title:Spatially and non-spatially tuned hippocampal neurons are linear perceptual and nonlinear memory encoders",
    ),
    # Arxiv, by title
    (arxiv_title, "title:Attention Is All You Need"),
    (arxiv_title, "title:Characterizing Idioms: Conventionality and Contingency"),
]

# biorxiv links sometimes fails with requests.exceptions.HTTPError: 421 Client
# Error: Misdirected Request
links_w_redirect_errors = {
    "10.1101/2020.10.29.359778",
    "10.1101/2023.05.17.541168",
    "10.1101/2023.10.27.564468",
    "10.1101/2024.02.13.580150",
    "10.1101/2024.12.02.626449",
    "10.1101/2025.06.23.661173",
    "10.1101/2023.08.30.23294850",
}


@pytest.mark.parametrize(["func", "link"], links)
async def test_refine(func, link, dreg):
    typ, link = link.split(":", 1)
    try:
        result = await func(typ, link)
        assert result.authors
        dreg(result)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 421 and link in links_w_redirect_errors:
            pytest.skip(
                f"{link} fails with a misdirected request ending in error {e.response.status_code}"
            )
        else:
            raise


@pytest.mark.parametrize(
    ["func", "link"],
    [
        # Arxiv not indexed on CrossRef
        (crossref, "doi:10.48550/arXiv.2206.08164"),
        # We need the title to match exactly, CrossRef does not have this one
        (crossref_title, "title:Attention is All You Need"),
        # We need the title to match exactly
        (openalex_title, "title:Pre-training of Deep Bidirectional"),
    ],
)
async def test_ignored_links(func, link):
    typ, link = link.split(":")
    result = await func(typ, link)
    assert result is None
