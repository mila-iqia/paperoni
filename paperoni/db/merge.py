from ..model import AuthorMerge, PaperMerge


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
