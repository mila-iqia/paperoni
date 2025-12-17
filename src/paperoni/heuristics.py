from collections import deque
from dataclasses import replace

from .model import Institution, Paper, Release


def simplify_releases(releases: list[Release]):
    def score(rel):
        is_not_published = int(rel.status != "published")
        # lower precision value is less precise
        # (see DatePrecision Enum: unknown=0, year=1, month=2, day=3)
        precision = getattr(rel.venue, "date_precision", 0)
        date_val = rel.venue.date
        return (is_not_published, -precision, -date_val.toordinal())

    def simplify(r1, r2):
        if r1.venue.name.lower() == r2.venue.name.lower():
            delta_days = abs((r1.venue.date - r2.venue.date).days)
            if delta_days < 300:
                return r1 if score(r1) > score(r2) else r2
        return None

    candidates = deque(releases)
    results = []
    while candidates:
        c = candidates.popleft()
        for other in list(candidates):
            result = simplify(c, other)
            if result is not None:
                c = result
                candidates.remove(other)
        results.append(c)
    return results


def simplify_institutions(institutions: list[Institution]):
    # dicts preserve order, that's why we don't use a set
    return list({i: i for i in institutions}.values())


def simplify_paper(paper: Paper):
    return replace(
        paper,
        authors=[
            replace(
                author,
                affiliations=list({aff: aff for aff in author.affiliations}.values()),
            )
            for author in paper.authors
        ],
        releases=simplify_releases(paper.releases),
    )
