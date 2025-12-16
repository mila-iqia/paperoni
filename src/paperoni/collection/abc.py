from datetime import date
from typing import Iterable

from ..model.classes import CollectionPaper, Paper

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


class PaperCollection:
    @property
    def exclusions(self) -> set[str]:
        raise NotImplementedError()

    def add_papers(self, papers: Iterable[CollectionPaper]) -> int:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> CollectionPaper | None:
        raise NotImplementedError()

    def find_by_id(self, paper_id: int) -> CollectionPaper | None:
        raise NotImplementedError()

    def edit_paper(self, paper: CollectionPaper) -> None:
        raise NotImplementedError()

    def commit(self) -> None:
        raise NotImplementedError()

    def drop(self) -> None:
        raise NotImplementedError()

    def search(
        self,
        # Paper ID
        paper_id: str = None,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
        # Venue name (long or short)
        venue: str = None,
        # Start date to consider
        start_date: date = None,
        # End date to consider
        end_date: date = None,
        # Flags that must be True
        include_flags: list[str] = None,
        # Flags that must be False
        exclude_flags: list[str] = None,
    ) -> Iterable[CollectionPaper]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()
