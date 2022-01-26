from coleo import Option, default, tooled

from ..papers2 import Paper
from .interactive import InteractiveCommands, default_commands
from .command_semantic_scholar import search
from ..sql.collection import Collection

search_commands = InteractiveCommands(
    "Include this paper in the collection?", default="y"
)


@search_commands.register("y", "[y]es")
def _y(self, paper, collection: Collection):
    """Include the paper in the collection"""
    collection.add(paper)
    return True


@search_commands.register("n", "[n]o")
def _n(self, paper, collection: Collection):
    """Exclude the paper from the collection"""
    collection.exclude(paper)
    return True


@search_commands.register("s", "[s]kip")
def _s(self, paper, collection: Collection):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


@tooled
def command_collect_semantic_scholar():
    """Collect papers from the Senantic Scholar database."""

    # File containing the collection
    # [alias: -c]
    collection: Option & Collection

    # Command to run on every paper
    command: Option = default(None)

    # Prompt for papers even if they were excluded from the collection
    show_excluded: Option & bool = default(False)

    # Display long form for each paper
    long: Option & bool = default(False)

    # Update existing papers with new information
    update: Option & bool = default(False)

    # Include all papers from the collection
    # [options: --yes]
    yes_: Option & bool = default(False)

    if yes_:
        command = "y"

    # Exclude all papers from the collection
    # [options: --no]
    no_: Option & bool = default(False)

    if no_:
        command = "n"

    papers = search()

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
