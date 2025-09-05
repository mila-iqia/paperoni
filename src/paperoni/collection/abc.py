from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from ..model.classes import Paper


@dataclass
class CollectionMixin:
    id: int = None
    version: datetime = None

    @classmethod
    def make_collection_item(
        cls,
        item,
        *,
        next_id: Callable[[], int] = lambda: None,
        **defaults,
    ) -> "CollectionMixin":
        if not isinstance(item, CollectionMixin):
            fields = {**defaults, **vars(item)}
            item = cls(**fields)
        item.id = next_id() if item.id is None else item.id
        item.version = datetime.now() if item.version is None else item.version
        return item


@dataclass
class CollectionPaper(Paper, CollectionMixin):
    pass


class PaperCollection:
    @property
    def exclusions(self) -> set[str]:
        raise NotImplementedError()

    def add_papers(self, papers: Iterable[Paper | CollectionMixin]) -> None:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> CollectionMixin | None:
        raise NotImplementedError()
