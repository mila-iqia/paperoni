from paperoni.sources.scrapers.pdftools import PDF


def fulltext(paper, cache_policy="use"):
    for lnk in paper.links:
        pdf = PDF(lnk, cache_policy=cache_policy)
        text = pdf.get_fulltext(fulldata=False)
        if text is not None:
            return text
    return None
