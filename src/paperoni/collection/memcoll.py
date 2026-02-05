from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, AsyncGenerator, Iterable

from serieux import deserialize, serialize

from ..model.classes import Paper
from ..utils import (
    normalize_institution,
    normalize_name,
    normalize_title,
    normalize_venue,
    to_sync,
)
from .abc import PaperCollection
from .finder import Index, find_equivalent, paper_indexers


@dataclass
class PaperIndex(Index[Paper]):
    last_id: int = -1
    indexers: dict[str, Any] = field(default_factory=lambda: paper_indexers)
    exclusions: set[str] = field(default_factory=set)

    def next_id(self) -> int:
        self.last_id += 1
        return self.last_id

    def index(self, paper):
        if paper.id is None:
            paper.id = self.next_id()
        super().index(paper)

    def __iter__(self):
        for _, paper in sorted(self.indexes["latest"].items(), reverse=True):
            yield paper

    @classmethod
    def serieux_serialize(cls, obj, ctx, cn):
        return {
            "_last_id": serialize(int, obj.last_id, ctx),
            "_papers": serialize(list[Paper], list(obj), ctx),
            "_exclusions": serialize(set[str], obj.exclusions, ctx),
        }

    @classmethod
    def serieux_deserialize(cls, obj, ctx, cn):
        rval = cls(
            last_id=deserialize(int, obj["_last_id"]),
            exclusions=deserialize(set[str], obj["_exclusions"]),
        )
        rval.index_all(deserialize(list[Paper], obj["_papers"], ctx))
        return rval


@dataclass
class MemCollection(PaperCollection):
    def __post_init__(self):
        self._index = PaperIndex()

    async def exclusions(self) -> set[str]:
        return self._index.exclusions

    async def add_exclusions(self, exclusions: list[str]) -> None:
        """Add exclusion strings."""
        for exclusion in exclusions:
            self._index.exclusions.add(exclusion)
        if exclusions:
            await self.commit()

    async def remove_exclusions(self, exclusions: list[str]) -> None:
        """Remove exclusion strings."""
        for exclusion in exclusions:
            self._index.exclusions.discard(exclusion)
        if exclusions:
            await self.commit()

    async def is_excluded(self, s):
        """Return whether a link is excluded."""
        return s in self._index.exclusions

    async def add_papers(
        self, papers: Iterable[Paper], force=False, ignore_exclusions=False
    ) -> list[int | str]:
        added_ids = []
        if not ignore_exclusions:
            papers = await to_sync(self.filter_exclusions(papers))

        try:
            for p in papers:
                p = self.prepare(p)

                if paper := self._index.equiv("id", p):
                    if not force and paper.version >= p.version:
                        # Paper has been updated since last time it was fetched.
                        # Do not replace it.
                        continue
                    p.version = datetime.now()

                elif p.id is not None:
                    raise ValueError(f"Paper with ID {p.id} not found in collection")

                else:
                    p = replace(p, id=self._index.next_id(), version=datetime.now())
                    assert not self._index.equiv("id", p)

                added_ids.append(p.id)

                assert p.id is not None
                assert p.version is not None
                if paper:
                    # Replace existing paper
                    self._index.remove(paper)
                self._index.index(p)

        finally:
            if added_ids:
                self._commit()

        return added_ids

    async def delete_ids(self, ids: list[int]) -> int:
        deleted = 0
        try:
            for i in ids:
                if paper := self._index.find("id", i):
                    self._index.remove(paper)
                    deleted += 1
        finally:
            if deleted:
                self._commit()
        return deleted

    async def find_paper(self, paper: Paper) -> Paper | None:
        return find_equivalent(paper, self._index)

    async def find_by_id(self, paper_id: int) -> Paper | None:
        return self._index.find("id", paper_id)

    async def commit(self) -> None:
        self._commit()

    def _commit(self) -> None:
        # MemCollection, nothing to commit
        pass

    async def drop(self) -> None:
        self._index.last_index = -1
        self._index.exclusions.clear()
        self._index.indexes = {k: {} for k in self._index.indexes}
        await self.commit()

    async def search(
        self,
        # Paper ID
        paper_id: int | None = None,
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
        # Flags that must be present
        include_flags: list[str] = None,
        # Flags that must not be present
        exclude_flags: list[str] = None,
    ) -> AsyncGenerator[Paper, None]:
        if paper_id is not None:
            yield await self.find_by_id(paper_id)
            return

        title = title and normalize_title(title)
        author = author and normalize_name(author)
        institution = institution and normalize_institution(institution)
        venue = venue and normalize_venue(venue)
        for p in self._index:
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
            if include_flags and (set(include_flags) - p.flags):
                continue
            if exclude_flags and (set(exclude_flags) & p.flags):
                continue
            matching_releases = p.releases
            if venue:
                matching_releases = [
                    release
                    for release in p.releases
                    if (
                        venue in normalize_venue(release.venue.name)
                        or (
                            release.venue.short_name
                            and venue in normalize_venue(release.venue.short_name)
                        )
                        or any(
                            venue in normalize_venue(alias)
                            for alias in release.venue.aliases
                        )
                    )
                ]
                if not matching_releases:
                    continue
            if start_date and all(
                release.venue.date < start_date for release in matching_releases
            ):
                continue
            if end_date and all(
                end_date < release.venue.date for release in matching_releases
            ):
                continue
            yield p

    def __len__(self) -> int:
        return sum(1 for _ in self._index)
