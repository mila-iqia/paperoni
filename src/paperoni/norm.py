from dataclasses import dataclass, field
from datetime import date, datetime

from ovld import ovld, recurse
from serieux import Partial
from serieux.features.filebacked import FileProxy
from serieux.features.partial import NOT_GIVEN, instantiate, merge

from .model.classes import (
    Institution,
    Paper,
    PaperAuthor,
    Release,
    Venue,
)


@dataclass
class NormalizationEntry[T]:
    origin: str
    data: T


@dataclass
class PaperNormalizer:
    venue_norm: dict[str, NormalizationEntry[Partial[Venue]]] @ FileProxy(
        refresh=True
    ) = field(default_factory=dict)
    institution_norm: dict[str, NormalizationEntry[list[Partial[Institution]]]] @ FileProxy(
        refresh=True
    ) = field(default_factory=dict)

    @ovld
    def __call__(self, x: str | int | float | bool | type(None) | date | datetime):
        return x

    @ovld(priority=0)
    def __call__(self, x: object):
        """Pass-through for enums and other unhandled types."""
        return x

    @ovld
    def __call__(self, x: list):
        return [recurse(item) for item in x]

    @ovld
    def __call__(self, x: dict):
        return {k: recurse(v) for k, v in x.items()}

    @ovld
    def __call__(self, x: set):
        return {recurse(item) for item in x}

    @ovld
    def __call__(self, x: Institution):
        if entry := self.institution_norm.get(x.name, None):
            results = []
            for partial in entry.data:
                inst = instantiate(merge(x, partial))
                if isinstance(inst, Exception):
                    raise inst
                results.append(inst)
            return results if results else x
        return x

    @ovld
    def __call__(self, x: Venue):
        if entry := self.venue_norm.get(x.name, None):
            rval = instantiate(merge(x, entry.data))
            if (
                ep := entry.data.date_precision
            ) is not NOT_GIVEN and ep < x.date_precision:
                # Restore date if it has better precision than the normalizer's
                rval.date = x.date
                rval.date_precision = x.date_precision
            return rval
        else:
            return x

    @ovld
    def __call__(self, x: Release):
        return Release(
            venue=recurse(x.venue),
            status=x.status,
            pages=x.pages,
            peer_review_status=x.peer_review_status,
        )

    @ovld
    def __call__(self, x: PaperAuthor):
        affiliations = []
        for aff in x.affiliations:
            result = recurse(aff)
            if isinstance(result, list):
                affiliations.extend(result)
            else:
                affiliations.append(result)
        return PaperAuthor(
            author=x.author,
            display_name=x.display_name,
            affiliations=affiliations,
        )

    @ovld
    def __call__(self, p: Paper):
        return Paper(
            title=p.title,
            abstract=p.abstract,
            authors=recurse(p.authors),
            releases=recurse(p.releases),
            topics=p.topics,
            links=p.links,
            flags=p.flags,
            key=p.key,
            info=p.info,
            score=p.score,
            id=p.id,
            version=p.version,
        )
