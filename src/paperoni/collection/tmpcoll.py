from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from typing import Generator, Iterable

from ..model.classes import Link, Paper
from .abc import CollectionMixin, CollectionPaper, PaperCollection

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
class TmpCollection(PaperCollection):
    def __post_init__(self):
        self._last_id = -1
        self._papers: list[Paper | CollectionMixin] = []
        self._exclusions: set[str] = set()

    @property
    def exclusions(self) -> set[str]:
        return self._exclusions

    @cached_property
    def _by_id(self) -> dict[int, Paper | CollectionPaper]:
        return {}

    @cached_property
    def _by_title(self) -> dict[str, Paper | CollectionPaper]:
        return {}

    @cached_property
    def _by_link(self) -> dict[Link, Paper | CollectionPaper]:
        return {}

    def next_paper_id(self) -> int:
        # In case we added papers without incrementing the id, reset the first
        # id to the length of the papers
        self._last_id = max(
            self._last_id, len(self._papers) - 1, *[p.id for p in self._papers]
        )
        self._last_id += 1
        return self._last_id

    def add_papers(self, papers: Iterable[Paper | CollectionPaper]) -> int:
        added = 0

        for p in papers:
            for link in p.links:
                if f"{link.type}:{link.link}" in self.exclusions:
                    break

            else:
                if isinstance(p, CollectionMixin) and p.id in self._by_id:
                    paper = self._by_id[p.id]
                    if paper.version >= p.version:
                        # Paper has been updated since last time it was fetched.
                        # Do not replace it.
                        continue
                    self._papers.remove(paper)
                    p.version = datetime.now()

                else:
                    p = CollectionPaper.make_collection_item(
                        p, next_id=self.next_paper_id
                    )
                    assert p.id not in self._by_id

                self._papers.append(p)
                added += 1

                assert p.id is not None
                assert p.version is not None
                self._by_id[p.id] = p
                self._by_title[p.title.lower()] = p
                for link in p.links:
                    self._by_link[link] = p

        return added

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    self._exclusions.add(f"{link.type}:{link.link}")

    def find_paper(self, paper: Paper) -> Paper | CollectionPaper | None:
        for lnk in paper.links:
            if result := self._by_link.get(lnk, None):
                return result
        return self._by_title.get(paper.title.lower(), None)

    def search(
        self,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
    ) -> Generator[Paper | CollectionPaper, None, None]:
        title = title and title.lower()
        author = author and author.lower()
        institution = institution and institution.lower()
        for p in self._papers:
            if title and title not in p.title.lower():
                continue
            if author and not any(author in a.display_name.lower() for a in p.authors):
                continue
            if institution and not any(
                institution in aff.name.lower()
                for a in p.authors
                for aff in a.affiliations
            ):
                continue
            yield p
