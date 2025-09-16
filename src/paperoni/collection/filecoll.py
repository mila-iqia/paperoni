from dataclasses import dataclass, field
from pathlib import Path

from serieux import deserialize, dump, load, serialize

from ..model.classes import CollectionPaper
from .memcoll import MemCollection


@dataclass
class FileCollection(MemCollection):
    directory: Path = field(compare=False)
    _last_id: int = field(init=False, compare=False, default=None)
    _papers: list[CollectionPaper] = field(init=False, default_factory=list)
    _exclusions: set[str] = field(init=False, default_factory=set)

    def __post_init__(self):
        if self.directory is None:
            # If no directory is provided, use the MemCollection implementation
            self._file = None

            super().__post_init__()
            return

        self._file = self.directory / "collection.yaml"

        if self._file.exists():
            self.__dict__.update(vars(load(type(self), self._file)))

        else:
            self.directory.mkdir(exist_ok=True, parents=True)
            self.commit()

    def commit(self) -> None:
        if self._file is None:
            super().commit()
            return

        dump(type(self), self, dest=self._file)

    @classmethod
    def serieux_deserialize(cls, obj: dict, ctx, call_next):
        return deserialize(MemCollection, obj)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return serialize(MemCollection, obj)
