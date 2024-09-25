from paperoni.config import papconf
from paperoni.fulltext.locate import find_download_links

from ..common import one_test_per_assert


def sanitize(url):
    url = url.url
    for token in papconf.tokens.__dict__.values():
        url = url.replace(token, "REDACTED")
    return url


def fdl(link):
    return [sanitize(url) for url in find_download_links(link)]


@one_test_per_assert
def test_find_download_links(config_with_secrets):
    assert fdl("arxiv:2307.10312") == [
        "https://export.arxiv.org/pdf/2307.10312.pdf"
    ]
    assert fdl("openreview:DimPeeCxKO") == [
        "https://openreview.net/pdf?id=DimPeeCxKO"
    ]
    assert fdl(
        "pdf:https://raw.githubusercontent.com/mlresearch/v235/main/assets/liu24m/liu24m.pdf"
    ) == [
        "https://raw.githubusercontent.com/mlresearch/v235/main/assets/liu24m/liu24m.pdf"
    ]
    assert fdl(
        "pdf.official:https://raw.githubusercontent.com/mlresearch/v235/main/assets/liu24m/liu24m.pdf"
    ) == [
        "https://raw.githubusercontent.com/mlresearch/v235/main/assets/liu24m/liu24m.pdf"
    ]

    assert fdl("doi:10.1016/j.apenergy.2024.123433") == [
        "https://api.elsevier.com/content/article/doi/10.1016/j.apenergy.2024.123433?apiKey=REDACTED&httpAccept=application%2Fpdf",
        "https://doi.org/10.1016/j.apenergy.2024.123433",
    ]

    assert fdl("html:https://google.com") == []
    assert fdl("ca:caca:cacaca") == []
