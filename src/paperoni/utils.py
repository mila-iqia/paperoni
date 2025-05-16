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
