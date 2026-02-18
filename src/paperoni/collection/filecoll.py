import stat
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from serieux import deserialize
from serieux.features.filebacked import FileProxy

from .memcoll import MemCollection, PaperIndex


@dataclass(kw_only=True)
class FileCollection(MemCollection):
    file: Path = field(compare=False)
    read_only: bool = False

    def __post_init__(self):
        ann = FileProxy(default_factory=PaperIndex, refresh=True)
        self._index = deserialize(PaperIndex @ ann, str(self.file))

        # Check if file is read-only
        if self.read_only or (
            self.file.exists() and self.file.stat().st_mode & stat.S_IWRITE == 0
        ):
            self.read_only = True

    def _commit(self) -> None:
        if self.read_only:
            warnings.warn(
                f"Collection {self.file} is open in read-only mode, skipping commit."
            )
            return
        self._index.save()
