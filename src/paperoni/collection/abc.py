from datetime import date
from typing import AsyncGenerator, Iterable

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

    async def add_exclusions(self, exclusions: list[str]) -> None:
        """Add exclusion strings (e.g., ['arxiv:1234.5678', 'doi:10.1234/5678'])."""
        raise NotImplementedError()

    async def remove_exclusions(self, exclusions: list[str]) -> None:
        """Remove exclusion strings."""
        raise NotImplementedError()

    async def is_excluded(self, s: str):
        """Return whether a link is excluded."""
        raise NotImplementedError()

    async def filter_exclusions(self, papers: Iterable[Paper]) -> Iterable[Paper]:
        """Filter out papers based on exclusions."""
        return [
            p
            for p in papers
            if not any(
                [(await self.is_excluded(f"{lnk.type}:{lnk.link}")) for lnk in p.links]
            )
        ]

    async def add_papers(self, papers: Iterable[Paper], ignore_exclusions=False) -> int:
        """Add papers to the collection."""
        raise NotImplementedError()

    async def exclude_papers(self, papers: Iterable[Paper]) -> None:
        """Exclude papers from the collection."""
        exclusions = set()
        for paper in papers:
            for link in paper.links:
                if link.type in _id_types:
                    exclusions.add(f"{link.type}:{link.link}")

        await self.add_exclusions(exclusions)

    async def find_paper(self, paper: Paper) -> Paper | None:
        raise NotImplementedError()

    async def find_by_id(self, paper_id: int) -> Paper | None:
        raise NotImplementedError()

    async def edit_paper(self, paper: Paper) -> None:
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
    ) -> AsyncGenerator[Paper, None]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()
