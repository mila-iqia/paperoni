from coleo import Argument as Arg, default, tooled

from ..config import get_config
from ..io import ResearchersFile
from ..papers import Papers
from ..query import QueryManager
from .interactive import InteractiveCommands, default_commands
from .searchutils import search

search_commands = InteractiveCommands(
    "Enter a command (h or ? for help):", default="s"
)


@search_commands.register("b")
def _b(self, paper):
    """Generate bibtex"""
    print(paper.bibtex())
    return None


@search_commands.register("p")
def _p(self, paper):
    """Download the PDF"""
    if not paper.download_pdf():
        print("No PDF direct download link is available for this paper.")
        print(
            "Try to follow the paper's URLs (see the complete list"
            " with the l command)"
        )
    return None


@search_commands.register("s")
def _s(self, paper):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


@tooled
def command_search():
    """Query the Microsoft Academic database."""

    papers = search()

    for paper in papers:
        instruction = search_commands.process_paper(paper)
        if instruction is False:
            return instruction
