from coleo import Argument as Arg, default, tooled

from ..config import get_config
from ..io import ResearchersFile
from ..papers import Papers
from ..query import QueryManager

from .searchutils import search


@tooled
def command_bibtex():
    """Generate bibtex entries for a search."""

    papers = search()

    for paper in papers:
        print(paper.bibtex())
        print()
