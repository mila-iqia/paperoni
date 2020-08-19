from blessed import Terminal

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

    def register(self, key):
        def deco(fn):
            self[key] = fn

        return deco

    def process_paper(self, paper, command=None, **kwargs):
        """Process a paper interactively."""
        print("=" * 80)
        paper.format_term()
        print("=" * 80)

        opts = "/".join(
            [
                (f"[{key}]" if key == self.default else key)
                for key in self.keys()
            ]
        )
        prompt = f"{self.prompt} {opts} "

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


@default_commands.register("q")
def _q(self, paper, **_):
    """Quit the program"""
    return False


@default_commands.register("l")
def _l(self, paper, **_):
    """Display long form of the paper (all details)"""
    print("=" * 80)
    paper.format_term_long()
    print("=" * 80)
    return None


@default_commands.register("h")
def _h(self, paper, **_):
    """display this help"""
    print("-" * 80)
    for key, entry in sorted(
        (key, fn.__doc__) for key, fn in self.items() if fn.__doc__
    ):
        print(T.bold(key), entry)
    print("-" * 80)
    return None
