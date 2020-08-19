from coleo import tooled

from .searchutils import search_ext


@tooled
def command_bibtex():
    """Generate bibtex entries for a search."""
    papers = search_ext()

    for paper in papers:
        print(paper.bibtex())
        print()
