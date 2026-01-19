from dataclasses import dataclass, field
from pathlib import Path

from serieux import dump, load

from ..utils import deprox
from .memcoll import MemCollection


@dataclass(kw_only=True)
class FileCollection(MemCollection):
    file: Path = field(compare=False)

    def __post_init__(self):
        super().__post_init__()

        self.file = deprox(self.file)

        if not self.file.exists():
            self.file.parent.mkdir(exist_ok=True, parents=True)
            self._commit()

        self.__dict__.update(vars(load(MemCollection, self.file)))

    def _commit(self):
        dump(type(self), self, dest=self.file)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return call_next(MemCollection, obj, ctx)
