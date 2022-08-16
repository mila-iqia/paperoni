from collections import defaultdict

from ..model import AuthorMerge, MergeEntry, PaperMerge, VenueMerge
from ..tools import similarity


def _process_standard_rows(rows, eqv, cls):
    """Process the equivalences of a "standard row".

    A standard row has the following columns, in order:

    0. A name representing the equivalent ids to merge
    1. An ID (hex)
    2. A semicolon-separated sequence of IDs (hex1;hex2;...)
    3. An integer representing the quality of (1)
    4. A semicolon-separated sequence of integers, the qualities of (2)
    """
    for r in rows:
        ids = [r[1], *r[2].split(";")]
        quals = [r[3], *map(int, r[4].split(";"))]
        eqv.equiv_all(
            [MergeEntry(id=i, quality=q) for q, i in zip(quals, ids)],
            under=r[0],
            cls=cls,
        )


def merge_papers_by_shared_link(db, eqv):
    """Merge papers that share a link or ID."""
    results = db.session.execute(
        """
        SELECT
            p1.title,
            hex(p1.paper_id),
            group_concat(hex(p2.paper_id), ';'),
            p1.quality,
            group_concat(p2.quality, ';')
        FROM paper as p1
        JOIN paper as p2
        ON p1.paper_id > p2.paper_id
        JOIN paper_link as pl1
        ON pl1.paper_id == p1.paper_id
        JOIN paper_link as pl2
        ON pl2.paper_id == p2.paper_id
        WHERE pl1.type == pl2.type
        AND pl1.link == pl2.link
        GROUP BY p1.paper_id
        """
    )
    _process_standard_rows(results, eqv, PaperMerge)


def merge_authors_by_shared_link(db, eqv):
    """Merge authors that share a link or ID."""
    results = db.session.execute(
        """
        SELECT
            a1.name,
            hex(a1.author_id),
            group_concat(hex(a2.author_id), ';'),
            a1.quality,
            group_concat(a2.quality, ';')
        FROM author as a1
        JOIN author as a2
        ON a1.author_id > a2.author_id
        JOIN author_link as al1
        ON al1.author_id == a1.author_id
        JOIN author_link as al2
        ON al2.author_id == a2.author_id
        WHERE al1.type == al2.type
        AND al1.link == al2.link
        GROUP BY a1.author_id
        """
    )
    _process_standard_rows(results, eqv, AuthorMerge)


def merge_papers_by_name(db, eqv):
    """Merge papers with the same name."""
    results = db.session.execute(
        """
        SELECT
            p1.title,
            hex(p1.paper_id),
            group_concat(hex(p2.paper_id), ';'),
            p1.quality,
            group_concat(p2.quality, ';')
        FROM paper as p1
        JOIN paper as p2
        ON p1.paper_id > p2.paper_id
        WHERE p1.squashed = p2.squashed
        GROUP BY p1.paper_id
        """
    )
    _process_standard_rows(results, eqv, PaperMerge)


def merge_authors_by_name(db, eqv):
    """Merge authors with the same name."""
    results = db.session.execute(
        """
        SELECT
            a1.name,
            hex(a1.author_id),
            group_concat(hex(a2.author_id), ';'),
            a1.quality,
            group_concat(a2.quality, ';')
        FROM author as a1
        JOIN author as a2
        ON a1.author_id > a2.author_id
        WHERE a1.name = a2.name
        GROUP BY a1.author_id
        """
    )
    _process_standard_rows(results, eqv, AuthorMerge)


def merge_authors_by_position(db, eqv):
    """Merge authors from merged papers."""
    results = db.session.execute(
        """
        SELECT
            hex(a1.author_id),
            hex(a2.author_id),
            a1.name,
            a2.name,
            p.paper_id,
            a1.quality,
            a2.quality
        FROM author as a1
        JOIN author as a2
        ON a1.author_id > a2.author_id
        JOIN paper as p
        JOIN paper_author as pa1
        ON a1.author_id = pa1.author_id AND p.paper_id = pa1.paper_id
        JOIN paper_author as pa2
        ON a2.author_id = pa2.author_id AND p.paper_id = pa2.paper_id
        WHERE pa1.author_position = pa2.author_position
        """
    )
    by_paper = defaultdict(list)
    for r in results:
        id1, id2, name1, name2, paper, q1, q2 = r
        sim = similarity(name1, name2)
        by_paper[paper].append((sim, id1, id2, name1, name2, q1, q2))

    for paper, data in by_paper.items():
        if any(sim < 0.5 for sim, *_ in data):
            # Ignore papers that may have swapped or offset authors from
            # a version to another
            continue
        # The 0.5 threshold may appear a bit low, but we are trying to merge
        # e.g. "C. S. Lewis" with "Clive Staples Lewis". Some proper matches
        # are below 0.5 as well, but it is too noisy.
        for sim, id1, id2, name1, name2, q1, q2 in data:
            eqv.equiv_all(
                [
                    MergeEntry(id=id1, quality=q1),
                    MergeEntry(id=id2, quality=q2),
                ],
                under=name1,
                cls=AuthorMerge,
            )


def merge_venues_by_shared_link(db, eqv):
    """Merge venues that share a link or ID."""
    results = db.session.execute(
        """
        SELECT
            v1.name,
            hex(v1.venue_id),
            group_concat(hex(v2.venue_id), ';'),
            v1.quality,
            group_concat(v2.quality, ';')
        FROM venue as v1
        JOIN venue as v2
        ON v1.venue_id > v2.venue_id
        JOIN venue_link as vl1
        ON vl1.venue_id == v1.venue_id
        JOIN venue_link as vl2
        ON vl2.venue_id == v2.venue_id
        WHERE vl1.type == vl2.type
        AND vl1.link == vl2.link
        GROUP BY v1.venue_id
        """
    )
    _process_standard_rows(results, eqv, VenueMerge)
