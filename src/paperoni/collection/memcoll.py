from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import AsyncGenerator, Iterable

from ..model.classes import Paper
from ..utils import (
    normalize_institution,
    normalize_name,
    normalize_title,
    normalize_venue,
)
from .abc import PaperCollection, _id_types
from .finder import find_equivalent, paper_index


@dataclass(kw_only=True)
class MemCollection(PaperCollection):
    _last_id: int = field(compare=False, default=None)
    _papers: list[Paper] = field(default_factory=list)
    _exclusions: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self._last_id is None:
            self._last_id = -1

        self._index = paper_index()
        if self._papers:
            assert self._last_id > -1, "If papers are provided, last id must be set"
            assert self._last_id >= max(
                len(self._papers) - 1, *[p.id for p in self._papers]
            ), "Last id must be at least equal to the maximum paper id"
            self._index.index_all(self._papers)

    async def exclusions(self) -> set[str]:
        return self._exclusions

    def next_id(self) -> int:
        self._last_id += 1
        return self._last_id

    async def add_papers(self, papers: Iterable[Paper]) -> int:
        return self._add_papers(papers)

    def _add_papers(self, papers: Iterable[Paper]) -> int:
        added = 0

        try:
            for p in papers:
                for link in p.links:
                    if f"{link.type}:{link.link}" in self._exclusions:
                        break

                else:
                    if paper := self._index.equiv("id", p):
                        if paper.version >= p.version:
                            # Paper has been updated since last time it was fetched.
                            # Do not replace it.
                            continue
                        self._papers.remove(paper)
                        p.version = datetime.now()

                    else:
                        p = replace(p, id=self.next_id(), version=datetime.now())
                        assert not self._index.equiv("id", p)

                    self._papers.append(p)
                    added += 1

                    assert p.id is not None
                    assert p.version is not None
                    self._index.index(p)

        finally:
            if added:
                self._commit()

        return added

    async def exclude_papers(self, papers: Iterable[Paper]) -> None:
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    self._exclusions.add(f"{link.type}:{link.link}")

        if papers:
            await self.commit()

    async def find_paper(self, paper: Paper) -> Paper | None:
        return find_equivalent(paper, self._index)

    async def find_by_id(self, paper_id: int) -> Paper | None:
        return self._index.find("id", paper_id)

    async def edit_paper(self, paper: Paper) -> None:
        for i, existing_paper in enumerate(self._papers):
            # TODO: we have to do this loop to find the index in the list,
            # this is not acceptable, but we'll fix it later
            if existing_paper.id == paper.id:
                paper.version = datetime.now()
                self._papers[i] = paper
                self._index.replace(paper)
                await self.commit()
                return

        raise ValueError(f"Paper with ID {paper.id} not found in collection")

    async def commit(self) -> None:
        self._commit()

    def _commit(self) -> None:
        # MemCollection, nothing to commit
        pass

    async def drop(self) -> None:
        self._last_id = -1
        self._papers.clear()
        self._exclusions.clear()
        self._index = paper_index()
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
        return len(self._papers)
