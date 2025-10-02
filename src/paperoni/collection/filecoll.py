from dataclasses import dataclass, field
from pathlib import Path

from serieux import dump, load

from ..model.classes import CollectionPaper
from .memcoll import MemCollection


@dataclass
class FileCollection(MemCollection):
    file: Path = field(compare=False)
    _last_id: int = field(init=False, compare=False, default=None)
    _papers: list[CollectionPaper] = field(init=False, default_factory=list)
    _exclusions: set[str] = field(init=False, default_factory=set)

    def __post_init__(self):
        super().__post_init__()

        if self.file.exists():
            self.__dict__.update(vars(load(type(self), self.file)))

        else:
            self.file.parent.mkdir(exist_ok=True, parents=True)
            self.commit()

    def commit(self) -> None:
        dump(type(self), self, dest=self.file)

    @classmethod
    def serieux_deserialize(cls, obj: dict, ctx, call_next):
        return call_next(MemCollection, obj, ctx)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return call_next(MemCollection, obj, ctx)
