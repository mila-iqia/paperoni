from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, AsyncGenerator, Iterable
from uuid import uuid4

from serieux import deserialize, serialize

from ..model.classes import Paper
from ..utils import (
    normalize_institution,
    normalize_name,
    normalize_title,
    normalize_topic,
    normalize_venue,
    to_sync,
)
from .abc import PaperCollection
from .finder import Index, find_equivalent, paper_indexers


def _make_matcher(query, normalize):
    """Build a predicate that matches a raw value against ``query``.

    A leading '=' in the query requests an exact match; otherwise the value
    matches if it contains the query as a substring. Both sides are compared
    after normalization.
    """
    exact = False
    if query.startswith("="):
        query = query[1:]
        exact = True
    needle = normalize(query)
    if exact:
        return lambda value: needle == normalize(value)
    else:
        return lambda value: needle in normalize(value)


@dataclass
class PaperIndex(Index[Paper]):
    last_id: int = -1
    indexers: dict[str, Any] = field(default_factory=lambda: paper_indexers)
    exclusions: set[str] = field(default_factory=set)

    def next_id(self) -> str:
        return str(uuid4())

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

                elif p.id is not None and not force:
                    raise ValueError(f"Paper with ID {p.id} not found in collection")

                else:
                    if p.id is None:
                        p = replace(p, id=self._index.next_id(), version=datetime.now())
                    elif p.version is None:
                        p = replace(p, version=datetime.now())
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

    async def find_by_id(self, paper_id: str) -> Paper | None:
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
        paper_id: str | None = None,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
        # Venue name (long or short)
        venue: str = None,
        # Topics the paper must have (all of them must match)
        topic: list[str] = None,
        # Start date to consider
        start_date: date = None,
        # End date to consider
        end_date: date = None,
        # Release statuses to match exactly; entries of the form "-xyz" exclude
        status: list[str] = None,
        # Flags that must be present
        include_flags: list[str] = None,
        # Flags that must not be present
        exclude_flags: list[str] = None,
        # Maximum number of results to yield
        limit: int = 0,
        # Number of results to skip
        offset: int = 0,
    ) -> AsyncGenerator[Paper, None]:
        if paper_id is not None:
            yield await self.find_by_id(paper_id)
            return

        title_match = title and _make_matcher(title, normalize_title)
        # An "@" in the author query switches the search to the email field.
        author_by_email = author and "@" in author
        if author_by_email:
            author_match = _make_matcher(author, str.lower)
        else:
            author_match = author and _make_matcher(author, normalize_name)
        institution_match = institution and _make_matcher(
            institution, normalize_institution
        )
        venue_match = venue and _make_matcher(venue, normalize_venue)
        topic_matchers = [_make_matcher(t, normalize_topic) for t in topic or []]
        include_status = [s for s in status or [] if not s.startswith("-")]
        exclude_status = [s[1:] for s in status or [] if s.startswith("-")]
        skipped = 0
        yielded = 0
        for p in self._index:
            if title_match and not title_match(p.title):
                continue
            if author_by_email:
                if not any(
                    a.author.email and author_match(a.author.email) for a in p.authors
                ):
                    continue
            elif author_match and not any(
                author_match(a.display_name) for a in p.authors
            ):
                continue
            if institution_match and not any(
                institution_match(aff.name) for a in p.authors for aff in a.affiliations
            ):
                continue
            if topic_matchers and not all(
                any(m(t.name) for t in p.topics) for m in topic_matchers
            ):
                continue
            if include_flags and (set(include_flags) - p.flags):
                continue
            if exclude_flags and (set(exclude_flags) & p.flags):
                continue
            if venue_match or start_date or end_date or include_status or exclude_status:
                # A single release must satisfy the venue, date and status
                # constraints together (mirrors $elemMatch in the mongo backend).
                def release_matches(release):
                    if venue_match and not (
                        venue_match(release.venue.name)
                        or (
                            release.venue.short_name
                            and venue_match(release.venue.short_name)
                        )
                        or any(venue_match(alias) for alias in release.venue.aliases)
                    ):
                        return False
                    if start_date and release.venue.date < start_date:
                        return False
                    if end_date and end_date < release.venue.date:
                        return False
                    if (
                        include_status
                        and release.peer_review_status not in include_status
                    ):
                        return False
                    if exclude_status and release.peer_review_status in exclude_status:
                        return False
                    return True

                if not any(release_matches(release) for release in p.releases):
                    continue

            if offset > 0 and skipped < offset:
                skipped += 1
                continue

            yield p
            yielded += 1
            if limit > 0 and yielded >= limit:
                break

    async def count(
        self,
        paper_id: str | None = None,
        title: str = None,
        institution: str = None,
        author: str = None,
        venue: str = None,
        topic: list[str] = None,
        start_date: date = None,
        end_date: date = None,
        status: list[str] = None,
        include_flags: list[str] = None,
        exclude_flags: list[str] = None,
    ) -> int:
        n = 0
        async for _ in self.search(
            paper_id=paper_id,
            title=title,
            institution=institution,
            author=author,
            venue=venue,
            topic=topic,
            start_date=start_date,
            end_date=end_date,
            status=status,
            include_flags=include_flags,
            exclude_flags=exclude_flags,
        ):
            n += 1
        return n
