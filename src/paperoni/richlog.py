import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from serieux import TaggedSubclass, serialize


@dataclass(kw_only=True)
class LogEvent:
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TimeStamp(LogEvent):
    label: str


@dataclass
class ErrorOccurred(LogEvent):
    context: list[str]
    exception: TaggedSubclass[BaseException]


@dataclass
class ProgressiveCount(LogEvent):
    origin: str
    category: str
    count: int


@dataclass
class Statistic(LogEvent):
    name: str
    value: float


LogEntry = TaggedSubclass[LogEvent]


@dataclass
class Logger:
    path: Path
    _file: object = field(default=None, init=False, repr=False)

    def __enter__(self):
        self._file = open(self.path, "a")
        self.log(TimeStamp(label="start"))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self.log(TimeStamp(label="end"))
            self._file.close()
        return False

    def log(self, event: LogEvent | None) -> None:
        if event is None:
            return
        serialized = serialize(LogEntry, event)
        json_line = json.dumps(serialized)
        self._file.write(json_line)
        self._file.write("\n")
