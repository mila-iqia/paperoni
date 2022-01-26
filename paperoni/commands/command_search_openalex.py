from coleo import Option, default, tooled

from ..papers2 import Paper
from .searchutils import search_openalex as search
from .interactive import InteractiveCommands, default_commands

search_commands = InteractiveCommands("Enter a command", default="s")


@search_commands.register("s", "[s]kip")
def _s(self, paper, **_):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


@tooled
def command_search_openalex():
    """Query the OpenAlex database."""

    # Command to run on every paper
    command: Option = default(None)

    # Display long form for each paper
    long: Option & bool = default(False)

    papers = search()

    sch = search_commands

    for paper in papers:
        instruction = sch.process_paper(
            paper,
            command=command,
            formatter=Paper.format_term_long if long else Paper.format_term,
        )
        if instruction is False:
            break
