import sys

import pkg_resources
from coleo import auto_cli

from .utils import PaperoniError


def main():
    commands = {}
    for entry_point in pkg_resources.iter_entry_points("paperoni.command"):
        commands[entry_point.name] = entry_point.load()
    try:
        auto_cli(commands, expand="@", print_result=False)
    except PaperoniError as err:
        print(f"{type(err).__name__}:", err.args[0], file=sys.stderr)
        sys.exit(1)
