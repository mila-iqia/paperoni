from coleo import Argument as Arg, default, tooled

from ..config import get_config
from ..io import PapersFile, ResearchersFile
from ..papers import Papers
from ..query import QueryManager
from .interactive import InteractiveCommands, default_commands
from .searchutils import search

search_commands = InteractiveCommands(
    "Enter a command (h or ? for help):", default="y"
)


@search_commands.register("y")
def _y(self, paper, collection):
    """Include the paper in the collection"""
    collection.add(paper)
    return True


@search_commands.register("n")
def _n(self, paper, collection):
    """Exclude the paper from the collection"""
    collection.exclude(paper)
    return True


@search_commands.register("s")
def _s(self, paper, collection):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


@tooled
def command_collect():
    """Collect papers from the Microsoft Academic database."""

    # File containing the collection
    # [alias: -c]
    collection: Arg & PapersFile

    # Command to run on every paper
    command: Arg = default(None)

    # Include all papers from the collection
    # [options: --yes]
    yes_: Arg & bool = default(False)

    if yes_:
        command = "y"

    # Exclude all papers from the collection
    # [options: --no]
    no_: Arg & bool = default(False)

    if no_:
        command = "n"

    papers = search()

    for paper in papers:
        if paper in collection:
            continue
        instruction = search_commands.process_paper(
            paper, collection=collection, command=command,
        )
        if instruction is False:
            break

    collection.save()
