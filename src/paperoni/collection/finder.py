import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ovld import ovld, recurse

from ..model import PaperWorkingSet, Scored
from ..model.classes import Paper
from ..utils import normalize_name, normalize_title, quick_author_similarity


@dataclass
class Index[T]:
    indexers: dict[str, Callable]
    indexes: dict[str, dict[Any, T]] = None

    def __post_init__(self):
        self.indexes = {name: {} for name in self.indexers}

    def index_all(self, entries: Iterable[T]):
        for entry in entries:
            self.index(entry)

    def index(self, entry: T):
        for name, fn in self.indexers.items():
            idx = self.indexes[name]
            for value in fn(entry):
                idx[value] = entry

    def remove(self, entry: T):
        for name, fn in self.indexers.items():
            idx = self.indexes[name]
            for value in fn(entry):
                idx.pop(value)

    def replace(self, entry: T):
        old_entry = self.equiv("id", entry)
        if old_entry is not None:
            self.remove(old_entry)
        self.index(entry)

    def find(self, index: str, value: Any):
        return self.indexes[index].get(value, None)

    def equiv(self, index: str, model: T):
        idx = self.indexes[index]
        for value in self.indexers[index](model):
            if result := idx.get(value, None):
                return result
        else:
            return None


def find_equivalent(p: Paper, idx: Index):
    if result := idx.equiv("links", p):
        return result
    if same_title := idx.equiv("title", p):
        au1 = list(extract_authors(p))
        au2 = list(extract_authors(same_title))
        sim = quick_author_similarity(au1, au2)
        if sim >= 0.8:
            return same_title
        else:
            logging.warning(
                f"Title match but low author similarity ({sim:.2f}) for paper '{p.title}': {au1} vs {au2}"
            )
    return None


@ovld
def to_paper(p: PaperWorkingSet):
    yield from recurse(p.current)


@ovld
def to_paper(p: Scored):
    yield from recurse(p.value)


@to_paper.variant
def extract_title(p: Paper):
    yield normalize_title(p.title)


@to_paper.variant
def extract_id(p: Paper):
    yield p.id


@to_paper.variant
def extract_authors(p: Paper):
    for a in p.authors:
        yield normalize_name(a.display_name)


@to_paper.variant
def extract_latest(p: Paper):
    if p.releases:
        d = max(release.venue.date for release in p.releases)
        yield f"{d}::{p.id}"
    else:
        yield f"0::{p.id}"


@to_paper.variant
def extract_links(p: Paper):
    yield from p.links


paper_indexers = {
    "id": extract_id,
    "title": extract_title,
    "links": extract_links,
    "latest": extract_latest,
}


def paper_index():
    return Index(indexers=paper_indexers)
