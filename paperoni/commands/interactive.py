from blessed import Terminal

from ..papers import Paper

T = Terminal()


class InteractiveCommands(dict):
    """Collection of commands to interact with papers."""

    def __init__(self, prompt, default):
        self.prompt = prompt
        self.default = default

    def copy(self):
        rval = InteractiveCommands(self.prompt, self.default)
        rval.update(self)
        return rval

    def register(self, key, longkey):
        def deco(fn):
            fn._longkey = longkey
            self[key] = fn

        return deco

    def process_paper(
        self, paper, command=None, formatter=Paper.format_term, **kwargs
    ):
        """Process a paper interactively."""
        print("=" * 80)
        formatter(paper)
        print("=" * 80)

        opts = " ".join(
            [
                f"{T.underline(fn._longkey):18}"
                if key == self.default
                else f"{fn._longkey:10}"
                for key, fn in self.items()
            ]
        )
        print(opts)
        prompt = f"{self.prompt} (default: {self.default}): "

        while True:
            try:
                if command is None:
                    answer = input(prompt).strip()
                else:
                    answer = command
            except (KeyboardInterrupt, EOFError):
                return False
            if not answer:
                answer = self.default
            if answer not in self:
                answer = "h"
            instruction = self[answer](self, paper, **kwargs)
            if command is not None or instruction is not None:
                return instruction


default_commands = InteractiveCommands(None, None)


@default_commands.register("q", "[q]uit")
def _q(self, paper, **_):
    """Quit the program"""
    return False


@default_commands.register("l", "[l]ong")
def _l(self, paper, **_):
    """Display long form of the paper (all details)"""
    print("=" * 80)
    paper.format_term_long()
    print("=" * 80)
    return None


@default_commands.register("h", "[h]elp")
def _h(self, paper, **_):
    """display this help"""
    print("-" * 80)
    for key, entry in sorted(
        (key, fn.__doc__) for key, fn in self.items() if fn.__doc__
    ):
        print(T.bold(key), entry)
    print("-" * 80)
    return None
