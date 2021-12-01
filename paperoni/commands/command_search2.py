import sys

from coleo import Option, default, tooled

from ..papers2 import Paper
from .interactive import InteractiveCommands, default_commands
from .searchutils import search_sql
from ..sql.collection import Collection, MutuallyExclusiveError

search_commands = InteractiveCommands("Enter a command", default="s")


@search_commands.register("p", "[p]df")
def _p(self, paper: Paper, **_):
    """Download the PDF"""
    if not paper.download_pdf():
        print("No PDF direct download link is available for this paper.")
        print(
            "Try to follow the paper's URLs (see the complete list"
            " with the l command)"
        )
    return None


@search_commands.register("s", "[s]kip")
def _s(self, paper, **_):
    """Skip and see the next paper"""
    return True


@search_commands.register("r", "[r]emove")
def _r(self, paper: Paper, collection: Collection):
    """Remove the paper from the collection"""
    collection.exclude(paper)
    print(f"Removed '{paper.title}' from collection")
    return True


search_commands.update(default_commands)


@tooled
def command_search2():
    """Query the Microsoft Academic database."""

    # File containing the collection
    # [alias: -c]
    collection: Option & Collection

    # Command to run on every paper
    command: Option = default(None)

    # Display long form for each paper
    long: Option & bool = default(False)

    try:
        for paper in search_sql(collection=collection):
            instruction = search_commands.process_paper(
                paper,
                command=command,
                collection=collection,
                formatter=Paper.format_term_long if long else Paper.format_term,
            )
            if instruction is False:
                break
    except MutuallyExclusiveError as exc:
        sys.exit(exc)

    collection.save()
