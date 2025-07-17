import pytest
from serieux import serialize

from paperoni.model.classes import Paper
from paperoni.refinement.dblp import dblp
from paperoni.refinement.doi import biorxiv, crossref, datacite, unpaywall
from paperoni.refinement.pubmed import pubmed

links = [
    # Crossref
    (crossref, "doi:10.1002/mp.17782"),
    (crossref, "doi:10.1007/s41109-021-00378-3"),
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
    # BiorXiv
    (biorxiv, "doi:10.1101/2020.10.29.359778"),
    (biorxiv, "doi:10.1101/2023.05.17.541168"),
    (biorxiv, "doi:10.1101/2023.10.27.564468"),
    (biorxiv, "doi:10.1101/2024.02.13.580150"),
    (biorxiv, "doi:10.1101/2024.12.02.626449"),
    (biorxiv, "doi:10.1101/2025.06.23.661173"),
    (biorxiv, "doi:10.1101/2023.08.30.23294850"),
    # DBLP
    (dblp, "dblp:conf/icml/LachapelleDMMBL23"),
    (dblp, "dblp:conf/wacv/DaultaniL24"),
    (dblp, "dblp:conf/nips/LacosteLRSKLIDA23"),
    (dblp, "dblp:conf/icse-chase/AryaGR25"),
    (dblp, "dblp:conf/aaai/Rezaei-Shoshtari23"),
    # Pubmed Central
    (pubmed, "pmc:8900797"),
    (pubmed, "pmc:11551764"),
    (pubmed, "pmc:12136731"),
    (pubmed, "pmc:11971501"),
    (pubmed, "pmc:10684502"),
]


@pytest.mark.parametrize(["func", "link"], links)
def test_refine(func, link, data_regression):
    typ, link = link.split(":")
    result = func(typ, link)
    assert result.authors
    data = serialize(Paper, result)
    data_regression.check(data)


@pytest.mark.parametrize(
    ["func", "link"],
    [
        (crossref, "doi:10.48550/arXiv.2206.08164"),
        (dblp, "dblp:conf/corr/icml/LachapelleDMMBL23"),
    ],
)
def test_ignored_links(func, link):
    typ, link = link.split(":")
    result = func(typ, link)
    assert result is None
