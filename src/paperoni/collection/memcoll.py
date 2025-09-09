from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Generator, Iterable

from ..model.classes import CollectionMixin, CollectionPaper, Paper
from ..utils import normalize_institution, normalize_name, normalize_title
from .abc import PaperCollection
from .finder import Finder

_id_types = {
    "arxiv",
    "dblp",
    "doi",
    "mlr",
    "openalex",
    "openreview",
    "pmc",
    "pubmed",
    "semantic_scholar",
    "uid",
}


@dataclass
class MemCollection(PaperCollection):
    _last_id: int = field(compare=False, default=None)
    _papers: list[CollectionPaper] = field(default_factory=list)
    _exclusions: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self._last_id is None:
            self._last_id = -1

        self._finder = Finder()
        if self._papers:
            assert self._last_id > -1, "If papers are provided, last id must be set"
            assert self._last_id >= max(
                len(self._papers) - 1, *[p.id for p in self._papers]
            ), "Last id must be at least equal to the maximum paper id"
            self._finder.add(self._papers)

    @property
    def exclusions(self) -> set[str]:
        return self._exclusions

    def next_id(self) -> int:
        self._last_id += 1
        return self._last_id

    def add_papers(self, papers: Iterable[CollectionPaper]) -> int:
        added = 0

        try:
            for p in papers:
                for link in p.links:
                    if f"{link.type}:{link.link}" in self.exclusions:
                        break

                else:
                    if isinstance(p, CollectionMixin) and p.id in self._finder.by_id:
                        paper = self._finder.by_id[p.id]
                        if paper.version >= p.version:
                            # Paper has been updated since last time it was fetched.
                            # Do not replace it.
                            continue
                        self._papers.remove(paper)
                        p.version = datetime.now()

                    else:
                        p = CollectionPaper.make_collection_item(p, next_id=self.next_id)
                        assert p.id not in self._finder.by_id

                    self._papers.append(p)
                    added += 1

                    assert p.id is not None
                    assert p.version is not None
                    self._finder.add([p])

        finally:
            if added:
                self.commit()

        return added

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    self._exclusions.add(f"{link.type}:{link.link}")

        if papers:
            self.commit()

    def find_paper(self, paper: Paper) -> CollectionPaper | None:
        return self._finder.find(paper)

    def search(
        self,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
        # Start date to consider
        start_date: date = None,
        # End date to consider
        end_date: date = None,
    ) -> Generator[CollectionPaper, None, None]:
        title = title and normalize_title(title)
        author = author and normalize_name(author)
        institution = institution and normalize_institution(institution)
        for p in self._papers:
            if title and title not in normalize_title(p.title):
                continue
            if author and not any(
                author in normalize_name(a.display_name) for a in p.authors
            ):
                continue
            if institution and not any(
                institution in normalize_institution(aff.name)
                for a in p.authors
                for aff in a.affiliations
            ):
                continue
            if start_date and all(
                release.venue.date < start_date for release in p.releases
            ):
                continue
            if end_date and all(end_date < release.venue.date for release in p.releases):
                continue
            yield p

    def commit(self) -> None:
        # MemCollection, nothing to commit
        pass

    def __len__(self) -> int:
        return len(self._papers)
