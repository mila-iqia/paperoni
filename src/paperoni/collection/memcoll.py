from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Generator, Iterable

from ..model.classes import CollectionMixin, CollectionPaper, Paper
from ..utils import (
    normalize_institution,
    normalize_name,
    normalize_title,
    normalize_venue,
)
from .abc import PaperCollection, _id_types
from .finder import Finder


@dataclass(kw_only=True)
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

    def find_by_id(self, paper_id: int) -> CollectionPaper | None:
        return self._finder.by_id.get(paper_id)

    def edit_paper(self, paper: CollectionPaper) -> None:
        for i, existing_paper in enumerate(self._papers):
            # TODO: we have to do this loop to find the index in the list,
            # this is not acceptable, but we'll fix it later
            if existing_paper.id == paper.id:
                paper.version = datetime.now()
                self._papers[i] = paper
                self._finder.replace(paper)
                self.commit()
                return

        raise ValueError(f"Paper with ID {paper.id} not found in collection")

    def commit(self) -> None:
        # MemCollection, nothing to commit
        pass

    def drop(self) -> None:
        self._last_id = -1
        self._papers.clear()
        self._exclusions.clear()
        self._finder = Finder()
        self.commit()

    def search(
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
    ) -> Generator[CollectionPaper, None, None]:
        if paper_id is not None:
            yield self.find_by_id(paper_id)
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
