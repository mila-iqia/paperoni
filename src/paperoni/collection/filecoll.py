from dataclasses import dataclass, field
from pathlib import Path

from serieux import deserialize
from serieux.features.filebacked import FileProxy

from .memcoll import MemCollection, PaperIndex


@dataclass(kw_only=True)
class FileCollection(MemCollection):
    file: Path = field(compare=False)

    def __post_init__(self):
        ann = FileProxy(default_factory=PaperIndex, refresh=True)
        self._index = deserialize(PaperIndex @ ann, str(self.file))

    def _commit(self) -> None:
        self._index.save()
