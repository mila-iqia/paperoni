from coleo import Argument as Arg, default, tooled

from ..io import PapersFile, ResearchersFile
from .interactive import InteractiveCommands, default_commands
from .searchutils import search

search_commands = InteractiveCommands(
    "Enter a command (h or ? for help):", default="s"
)


@search_commands.register("b")
def _b(self, paper, **_):
    """Generate bibtex"""
    print(paper.bibtex())
    return None


@search_commands.register("p")
def _p(self, paper, **_):
    """Download the PDF"""
    if not paper.download_pdf():
        print("No PDF direct download link is available for this paper.")
        print(
            "Try to follow the paper's URLs (see the complete list"
            " with the l command)"
        )
    return None


@search_commands.register("s")
def _s(self, paper, **_):
    """Skip and see the next paper"""
    return True


search_commands_with_coll = search_commands.copy()


@search_commands_with_coll.register("r")
def _r(self, paper, collection):
    """Remove the paper from the collection"""
    collection.exclude(paper)
    print(f"Removed '{paper.title}' from collection")
    return True


search_commands.update(default_commands)
search_commands_with_coll.update(default_commands)


@tooled
def command_search():
    """Query the Microsoft Academic database."""

    # File containing the collection
    # [alias: -c]
    collection: Arg & PapersFile = default(None)

    # Researchers file (JSON)
    # [alias: -r]
    researchers: Arg & ResearchersFile = default(None)

    # Command to run on every paper
    command: Arg = default(None)

    papers = search(collection=collection, researchers=researchers)

    sch = search_commands if collection is None else search_commands_with_coll

    for paper in papers:
        instruction = sch.process_paper(
            paper, command=command, collection=collection
        )
        if instruction is False:
            break

    if collection is not None:
        collection.save()
