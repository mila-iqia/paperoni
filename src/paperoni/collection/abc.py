from datetime import date
from typing import AsyncIterable, Iterable

from ..model.classes import Paper

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
    async def exclusions(self) -> set[str]:
        raise NotImplementedError()

    async def add_papers(self, papers: Iterable[Paper]) -> int:
        raise NotImplementedError()

    async def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    async def find_paper(self, paper: Paper) -> Paper | None:
        raise NotImplementedError()

    async def find_by_id(self, paper_id: int) -> Paper | None:
        raise NotImplementedError()

    async def edit_paper(self, paper: Paper) -> None:
        raise NotImplementedError()

    async def commit(self) -> None:
        raise NotImplementedError()

    async def drop(self) -> None:
        raise NotImplementedError()

    async def search(
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
    ) -> AsyncIterable[Paper]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()
