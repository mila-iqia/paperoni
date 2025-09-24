from dataclasses import dataclass, field
from typing import Callable

from paperoni.utils import normalize_title

from ..model.classes import Paper


@dataclass
class Finder[T]:
    title_finder: Callable = lambda p: p.title
    links_finder: Callable = lambda p: p.links
    id_finder: Callable = lambda p: getattr(p, "id", None)
    by_title: dict[str, T] = field(default_factory=dict)
    by_link: dict[str, T] = field(default_factory=dict)
    by_id: dict[str, T] = field(default_factory=dict)

    def add(self, entries: list[T]):
        for entry in entries:
            for lnk in self.links_finder(entry):
                self.by_link[lnk] = entry
            self.by_title[normalize_title(self.title_finder(entry))] = entry
            if i := self.id_finder(entry):
                self.by_id[i] = entry

    def find(self, p: Paper):
        for lnk in p.links:
            if result := self.by_link.get(lnk, None):
                return result
        return self.by_title.get(normalize_title(p.title), None)
