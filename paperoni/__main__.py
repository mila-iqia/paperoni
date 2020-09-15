import sys

import pkg_resources
from coleo import run_cli

from .utils import PaperoniError


def main():
    commands = {}
    for entry_point in pkg_resources.iter_entry_points("paperoni.command"):
        commands[entry_point.name] = entry_point.load()
    try:
        run_cli(commands, expand="@")
    except PaperoniError as err:
        print(f"{type(err).__name__}:", err.args[0], file=sys.stderr)
        sys.exit(1)
