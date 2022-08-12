from collections import defaultdict

from ..model import AuthorMerge, PaperMerge
from ..tools import similarity


def merge_papers_by_shared_link(db, eqv):
    """Merge papers that share a link or ID."""
    results = db.session.execute(
        """
        SELECT
            hex(p1.paper_id),
            group_concat(hex(p2.paper_id), ';'),
            p1.title
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
    for r in results:
        ids = {r[0], *r[1].split(";")}
        eqv.equiv_all(ids, under=r[2], cls=PaperMerge)


def merge_authors_by_shared_link(db, eqv):
    """Merge authors that share a link or ID."""
    results = db.session.execute(
        """
        SELECT
            hex(a1.author_id),
            group_concat(hex(a2.author_id), ';'),
            a1.name
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
    for r in results:
        ids = {r[0], *r[1].split(";")}
        eqv.equiv_all(ids, under=r[2], cls=AuthorMerge)


def merge_papers_by_name(db, eqv):
    """Merge papers with the same name."""
    results = db.session.execute(
        """
        SELECT
            hex(p1.paper_id),
            group_concat(hex(p2.paper_id), ';'),
            p1.title
        FROM paper as p1
        JOIN paper as p2
        ON p1.paper_id > p2.paper_id
        WHERE p1.squashed = p2.squashed
        GROUP BY p1.paper_id
        """
    )
    for r in results:
        ids = {r[0], *r[1].split(";")}
        eqv.equiv_all(ids, under=r[2], cls=PaperMerge)


def merge_authors_by_name(db, eqv):
    """Merge authors with the same name."""
    results = db.session.execute(
        """
        SELECT
            hex(a1.author_id),
            group_concat(hex(a2.author_id), ';'),
            a1.name
        FROM author as a1
        JOIN author as a2
        ON a1.author_id > a2.author_id
        WHERE a1.name = a2.name
        GROUP BY a1.author_id
        """
    )
    for r in results:
        ids = {r[0], *r[1].split(";")}
        eqv.equiv_all(ids, under=r[2], cls=AuthorMerge)


def merge_authors_by_position(db, eqv):
    """Merge authors from merged papers."""
    results = db.session.execute(
        """
        SELECT
            hex(a1.author_id),
            hex(a2.author_id),
            a1.name,
            a2.name,
            p.paper_id
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
        id1, id2, name1, name2, paper = r
        sim = similarity(name1, name2)
        by_paper[paper].append((sim, id1, id2, name1, name2))

    for paper, data in by_paper.items():
        if any(sim < 0.5 for sim, *_ in data):
            # Ignore papers that may have swapped or offset authors from
            # a version to another
            continue
        # The 0.5 threshold may appear a bit low, but we are trying to merge
        # e.g. "C. S. Lewis" with "Clive Staples Lewis". Some proper matches
        # are below 0.5 as well, but it is too noisy.
        for sim, id1, id2, name1, name2 in data:
            eqv.equiv_all([id1, id2], under=name1, cls=AuthorMerge)
