import itertools
import re
import unicodedata

from unidecode import unidecode

link_generators = {
    "arxiv": {
        "abstract": "https://arxiv.org/abs/{}",
        "pdf": "https://arxiv.org/pdf/{}.pdf",
    },
    "pubmed": {
        "abstract": "https://pubmed.ncbi.nlm.nih.gov/{}",
    },
    "pmc": {
        "abstract": "https://www.ncbi.nlm.nih.gov/pmc/articles/{}",
    },
    "doi": {
        "abstract": "https://doi.org/{}",
    },
    "openreview": {
        "abstract": "https://openreview.net/forum?id={}",
        "pdf": "https://openreview.net/pdf?id={}",
    },
    "mlr": {
        "abstract": "https://proceedings.mlr.press/v{}.html",
    },
    "dblp": {"abstract": "https://dblp.uni-trier.de/rec/{}"},
    "semantic_scholar": {"abstract": "https://www.semanticscholar.org/paper/{}"},
    "openalex": {
        "abstract": "https://openalex.org/{}",
    },
    # Placeholder to parse ORCID links, although those are not exactly paper links
    "orcid": {"abstract": "https://orcid.org/{}"},
}


def expand_links_dict(links):
    pref = [
        "html.official",
        "pdf.official",
        "doi.abstract",
        "mlr.abstract",
        "mlr.pdf",
        "openreview.abstract",
        "openreview.pdf",
        "arxiv.abstract",
        "arxiv.pdf",
        "pubmed.abstract",
        "pmc.abstract",
        "dblp.abstract",
        "pdf",
        "html",
        "semantic_scholar.abstract",
        "corpusid",
        "mag",
        "xml",
        "patent",
        "unknown",
        "unknown_",
    ]
    results = []
    for link in links:
        if link.type in link_generators:
            results.extend(
                {
                    "type": f"{link.type}.{kind}",
                    "link": link.link,
                    "url": url.format(link.link),
                }
                for kind, url in link_generators[link.type].items()
            )
        else:
            results.append({"type": link.type, "link": link.link})
    results.sort(
        key=lambda dct: pref.index(dct["type"]) if dct["type"] in pref else 1_000
    )
    return results


url_extractors = {
    r"https?://[a-z.]*arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://[a-z.]*arxiv-vanity\.com/papers/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://(?:[^/]*)arxiv(?:[^/]*)\.cornell\.edu/abs/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://scirate\.com/arxiv/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://pubmed\.ncbi\.nlm\.nih\.gov/([^/]*)/": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pubmed/([^/]*)": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/([^/]*)": "pmc",
    r"https?://europepmc.org/article/PMC/([^/]*)": "pmc",
    r"https?://(?:dx\.)?doi\.org/(.*)": "doi",
    r"https?://(?:www\.)?openreview\.net/(?:pdf\?|forum\?)id=(.*)": "openreview",
    r"https?://dblp.uni-trier.de/db/([^/]+)/([^/]+)/[^/]+\.html#(.*)": "dblp",
    r"https?://dblp.uni-trier.de/rec/(.*).html": "dblp",
    r"https?://ror.org/(.*)": "ror",
}


def url_to_id(url: str) -> tuple[str, str]:
    """Return an ID from a URL.

    * Given a link to an arxiv abstract or pdf, return ``("arxiv", arxiv_id)``
    * Given a DOI link, return ``("doi", the_doi)``
    * etc.

    See the ``url_extractors`` dictionary for the regexps and corresponding ID type.
    ``url_to_id`` tries each extractor in order.
    """
    for pattern, key in url_extractors.items():
        if m := re.match(pattern, url):
            lnk = "/".join(m.groups())
            return (key, lnk)
    return None


class QueryError(Exception):
    pass


def asciiify(s: str) -> str:
    """Translate a string to pure ASCII, removing accents and the like.

    Non-ASCII characters that are not accented characters are removed.
    """
    norm = unicodedata.normalize("NFD", s)
    stripped = norm.encode("ASCII", "ignore")
    return stripped.decode("utf8")


def mostly_latin(s: str, threshold: float = 0.9) -> bool:
    """
    Returns True if at least `threshold` (default 0.9) of the characters in the string
    are ASCII or accented Latin characters.
    """
    ### LLM code
    if not s:
        return True
    total = 0
    good = 0
    for c in s:
        total += 1
        o = ord(c)
        if o < 128:
            good += 1
        else:
            # Check if it's an accented Latin character
            # Normalize and check if it decomposes to a Latin base
            decomp = unicodedata.normalize("NFD", c)
            base = decomp[0]
            if "LATIN" in unicodedata.name(base, ""):
                good += 1
    return good / total >= threshold


def plainify(name):
    name = unidecode(name).lower()
    name = re.sub(string=name, pattern="[()-]", repl=" ")
    name = re.sub(string=name, pattern="['.]", repl="")
    return name


def associate(l1, l2, key, threshold=0):
    el1 = list(enumerate(l1))
    el2 = list(enumerate(l2))
    sims = [
        (value, i1, i2)
        for (i1, x1), (i2, x2) in itertools.product(el1, el2)
        if (value := key(x1, x2)) > threshold
    ]
    sims.sort(key=lambda tup: -tup[0])
    mapping = {}
    n = len(l1)
    for _, i1, i2 in sims:
        if i1 not in mapping:
            mapping[i1] = l2[i2]
        if len(mapping) == n:
            break
    return [(x1, mapping.get(i1, None)) for i1, x1 in el1]
