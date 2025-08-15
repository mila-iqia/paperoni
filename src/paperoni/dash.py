from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal

from outsight import Fixture
from rich.console import Console, Group, RenderableType as Renderable
from rich.live import Live
from rich.progress import BarColumn, Progress, TextColumn
from rich.rule import Rule
from rich.table import Table


@dataclass
class History[T]:
    values: list[T] = field(default_factory=list)
    display: Literal["short", "long"] = "long"

    def __rich__(self):
        lines = [
            f"[bold white]{v}[/bold white]" if i == 0 else f"[dim]{v}[/dim]"
            for i, v in enumerate(reversed(self.values))
        ]
        joiner = "  " if self.display == "short" else "\n"
        return joiner.join(lines)


@dataclass(eq=False)
class Dash(Fixture):
    data: dict[str, object] = field(default_factory=dict)
    live: Live = None
    fade_time: float = 10

    @property
    def scope(self):
        return "global"

    def __post_init__(self):
        self.progress = Progress(
            TextColumn(" [bold blue]{task.fields[name]}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("{task.completed}/{task.total}"),
            expand=True,
            transient=True,
        )
        self.progress_bars = {}

    def make_table(self):
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan", no_wrap=True, width=20)
        table.add_column("Value", no_wrap=True)
        for key, value in self.data.items():
            table.add_row(
                str(key), value if isinstance(value, Renderable) else str(value)
            )
        return table

    def make_display(self):
        components = []
        if self.data:
            components.append(Rule())
            components.append(self.make_table())
        components.append(self.progress)
        if self.data:
            components.append(Rule())
        return Group(*components)

    def __setitem__(self, key, value):
        self.data[key] = value
        if self.live:
            self.live.update(self.make_display())

    def add_progress(self, name, current, total):
        if name not in self.progress_bars:
            task_id = self.progress.add_task("", name=name, total=total)
            self.progress_bars[name] = task_id
        else:
            task_id = self.progress_bars[name]
        self.progress.update(task_id, completed=current, total=total)

    @asynccontextmanager
    async def context(self):
        if self.live:
            yield self
        else:
            console = Console()
            with Live(self.make_display(), console=console, refresh_per_second=4) as live:
                self.live = live
                yield self
