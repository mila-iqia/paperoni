import logging
from dataclasses import dataclass, field
from typing import Callable

from ..model.classes import Paper
from ..utils import normalize_title, quick_author_similarity


@dataclass
class Finder[T]:
    title_finder: Callable = lambda p: p.title
    links_finder: Callable = lambda p: p.links
    authors_finder: Callable = lambda p: p.authors
    id_finder: Callable = lambda p: getattr(p, "id", None)
    by_title: dict[str, T] = field(default_factory=dict)
    by_link: dict[str, T] = field(default_factory=dict)
    by_id: dict[str, T] = field(default_factory=dict)

    def add(self, entries: list[T]):
        for entry in entries:
            for lnk in self.links_finder(entry):
                self.by_link[lnk] = entry
            self.by_title[normalize_title(self.title_finder(entry))] = entry
            if (i := self.id_finder(entry)) is not None:
                self.by_id[i] = entry

    def find(self, p: Paper):
        for lnk in p.links:
            if result := self.by_link.get(lnk, None):
                return result
        same_title = self.by_title.get(normalize_title(p.title), None)
        if same_title:
            au1 = {a.display_name for a in p.authors}
            au2 = {a.display_name for a in self.authors_finder(same_title)}
            sim = quick_author_similarity(au1, au2)
            if sim >= 0.8:
                return same_title
            else:
                logging.warning(
                    f"Title match but low author similarity ({sim:.2f}) for paper '{p.title}': {au1} vs {au2}"
                )
        return None

    def remove(self, entry: T):
        for lnk in self.links_finder(entry):
            self.by_link.pop(lnk, None)
        title_key = normalize_title(self.title_finder(entry))
        self.by_title.pop(title_key, None)
        if i := self.id_finder(entry):
            self.by_id.pop(i, None)

    def replace(self, entry: T):
        entry_id = self.id_finder(entry)
        if entry_id and (old_entry := self.by_id.get(entry_id)):
            self.remove(old_entry)
        self.add([entry])
