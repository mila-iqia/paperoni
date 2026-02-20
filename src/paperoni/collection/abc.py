from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import AsyncGenerator, Callable, Iterable

from serieux.features.registered import Referenced

from ..model.classes import Paper
from ..operations import OperationResult

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
class PaperCollection:
    operations: list[Referenced[object]] = field(default_factory=list)

    def prepare(self, p: Paper):
        for op in self.operations:
            p = op(p).new
        return p

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

    async def filter_exclusions(
        self, papers: Iterable[Paper]
    ) -> AsyncGenerator[Paper, None]:
        """Filter out papers based on exclusions."""
        for paper in papers:
            for lnk in paper.links:
                if await self.is_excluded(f"{lnk.type}:{lnk.link}"):
                    break
            else:
                yield paper

    async def add_papers(
        self, papers: Iterable[Paper], force=False, ignore_exclusions=False
    ) -> list[int | str]:
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

    async def find_by_id(self, paper_id: str) -> Paper | None:
        raise NotImplementedError()

    async def edit_paper(self, paper: Paper) -> None:
        paper.version = datetime.now()
        await self.add_papers([paper], force=True, ignore_exclusions=True)

    async def delete_ids(self, ids: list[str]) -> int:
        """Delete papers by ID."""
        raise NotImplementedError()

    async def delete_papers(self, papers: list[Paper]):
        await self.exclude_papers(papers)
        await self.delete_ids([p.id for p in papers if p.id is not None])

    async def drop(self) -> None:
        raise NotImplementedError()

    async def operate(
        self, operator: Callable[[Paper], OperationResult], **search_options
    ):
        """Operate over every paper in the dataset."""
        edits = []
        async for p in self.search(**search_options):
            result = operator(p)
            if result.changed:
                edits.append(result.new)
        return await self.add_papers(edits, force=True, ignore_exclusions=True)

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

    async def cached(self):
        from .memcoll import MemCollection

        if not hasattr(self, "_cached"):
            coll = MemCollection()
            await coll.add_papers([replace(p, id=None) async for p in self.search()])
            await coll.add_exclusions(await self.exclusions())
            self._cached = coll
        return self._cached

    def __len__(self) -> int:
        raise NotImplementedError()
