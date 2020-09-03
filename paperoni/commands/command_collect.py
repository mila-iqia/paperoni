from coleo import Argument as Arg, default, tooled

from ..io import PapersFile, ResearchersFile
from ..papers import Paper
from .interactive import InteractiveCommands, default_commands
from .searchutils import search

search_commands = InteractiveCommands(
    "Include this paper in the collection?", default="y"
)


@search_commands.register("y", "[y]es")
def _y(self, paper, collection):
    """Include the paper in the collection"""
    collection.add(paper)
    return True


@search_commands.register("n", "[n]o")
def _n(self, paper, collection):
    """Exclude the paper from the collection"""
    collection.exclude(paper)
    return True


@search_commands.register("s", "[s]kip")
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

    # Researchers file (JSON)
    # [alias: -r]
    researchers: Arg & ResearchersFile = default(None)

    # Command to run on every paper
    command: Arg = default(None)

    # Prompt for papers even if they were excluded from the collection
    show_excluded: Arg & bool = default(False)

    # Display long form for each paper
    long: Arg & bool = default(False)

    # Update existing papers with new information
    update: Arg & bool = default(False)

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

    papers = search(researchers=researchers)

    for paper in papers:
        if paper in collection:
            if update:
                collection.add(paper)
            continue
        if not show_excluded and collection.excludes(paper):
            continue
        instruction = search_commands.process_paper(
            paper,
            collection=collection,
            command=command,
            formatter=Paper.format_term_long if long else Paper.format_term,
        )
        if instruction is False:
            break

    collection.save()
