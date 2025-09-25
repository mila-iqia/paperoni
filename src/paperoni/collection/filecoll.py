from dataclasses import dataclass, field
from pathlib import Path

from serieux import dump, load

from ..model.classes import CollectionPaper
from ..utils import deprox
from .memcoll import MemCollection


@dataclass(kw_only=True)
class FileCollection(MemCollection):
    file: Path = field(compare=False)
    _last_id: int = field(compare=False, default=None)
    _papers: list[CollectionPaper] = field(default_factory=list)
    _exclusions: set[str] = field(default_factory=set)

    def __post_init__(self):
        super().__post_init__()

        self.file = deprox(self.file)

        if not self.file.exists():
            self.file.parent.mkdir(exist_ok=True, parents=True)
            self.commit()

        self.__dict__.update(vars(load(MemCollection, self.file)))

    def commit(self) -> None:
        dump(type(self), self, dest=self.file)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return call_next(MemCollection, obj, ctx)
