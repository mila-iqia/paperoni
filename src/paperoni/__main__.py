import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml
from gifnoc import add_overlay, cli
from serieux import Auto, Registered, Tagged, TaggedUnion, serialize, singleton

from .config import discoverers
from .display import display, terminal_width
from .model import Paper


class Formatter(Registered):
    pass


@singleton("json")
class JSONFormatter(Formatter):
    def __call__(self, papers):
        ser = serialize(list[Paper], list(papers))
        print(json.dumps(ser, indent=4))


@singleton("yaml")
class YAMLFormatter(Formatter):
    def __call__(self, papers):
        ser = serialize(list[Paper], list(papers))
        print(yaml.safe_dump(ser, sort_keys=False))


@singleton("terminal")
class TerminalFormatter(Formatter):
    def __call__(self, papers):
        for i, paper in enumerate(papers):
            if i == 0:
                print("=" * terminal_width)
            display(paper)
            print("=" * terminal_width)


def make_cli():
    # Explanation:
    # * Auto[func] creates a virtual type based on the argument names and types of func
    # * Tagged[T, k] represents type T, but tagged with key k
    # * So we build a tuple of tagged types that represent the query functions of all
    #   registered discoverers
    # * In cli(...), a tagged union represents a subcommand, so each key in the tagged
    #   types will add a new subcommand with arguments that correspond to the function
    query_functions = tuple(Tagged[Auto[v.query], k] for k, v in discoverers.items())

    @dataclass
    class Discover:
        """Discover papers from various sources."""

        command: Union[query_functions]

        # Output format
        format: Formatter = TerminalFormatter

        def run(self):
            self.format(self.command())

    @dataclass
    class PaperoniInterface:
        """Paper database"""

        command: TaggedUnion[Discover]

        def run(self):
            self.command.run()

    return PaperoniInterface


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=None)
    args, remaining = parser.parse_known_args()
    if args.config:
        add_overlay(Path(args.config))

    PaperoniInterface = make_cli()

    command = cli(field="paperoni.cli", type=PaperoniInterface, argv=remaining)
    command.run()


if __name__ == "__main__":
    main()
