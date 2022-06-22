"""Collection class to manage a SQL database."""
import pprint
from typing import List, Union, Optional
from paperoni.papers2 import (
    Paper,
    Link,
    Author,
    Venue,
    Release,
    Topic,
    SOURCE_TYPES,
)
from paperoni.sql.database import Database
from paperoni.utils import get_venue_name_and_volume


class MutuallyExclusiveError(RuntimeError):
    """
    Exception raised when concurrent parameters are passed to
    Collection.query().
    """

    def __init__(self, *args):
        self.args = args

    def __str__(self):
        return "Mutually exclusive parameters: " + " vs ".join(
            self._param_to_str(arg) for arg in self.args
        )

    def _param_to_str(self, param):
        return param if isinstance(param, str) else f"({', '.join(param)})"


class Shortener:
    """
    Helper class to generate short names for tables.
    Used to generate JOIN statements in SQL queries.
    """

    __slots__ = ("long_to_short", "short_names")

    def __init__(self):
        self.long_to_short = {}
        self.short_names = set()

    def gen(self, snake_name: str):
        """Generate and stock a short name for given name."""
        if snake_name in self.long_to_short:
            return self.long_to_short[snake_name]
        short_name = "".join(piece[0] for piece in snake_name.split("_"))
        if short_name in self.short_names:
            index = 2
            while True:
                name = f"{short_name}{index}"
                if name in self.short_names:
                    index += 1
                else:
                    self.long_to_short[snake_name] = name
                    self.short_names.add(name)
                    return name
        else:
            self.long_to_short[snake_name] = short_name
            self.short_names.add(short_name)
            return short_name

    def __getitem__(self, snake_name):
        """Return short name for given name."""
        return self.long_to_short[snake_name]


class Collection:
    __slots__ = ("db", "papers_added", "papers_excluded")

    # Tables required for each parameter of Collection.query().
    PARAM_TO_TABLES = {
        "title": ["paper"],
        "words": ["paper"],
        "keywords": ["topic"],
        "author": ["paper_author", "author",],
        "institution": ["paper_author"],
        "venue": ["venue"],
        "year": ["release"],
        "start": ["release"],
        "end": ["release"],
        "recent": ["release"],
        "cited": ["paper"],
    }

    # Jointures required to reach a target table from `paper` table.
    # Used in Collection.query().
    TABLE_TO_JOINTURES = {
        "topic": [
            ("paper", "paper_topic", "paper_id"),
            ("paper_topic", "topic", "topic_id"),
        ],
        "paper_author": [("paper", "paper_author", "paper_id")],
        "author": [
            ("paper", "paper_author", "paper_id"),
            ("paper_author", "author", "author_id"),
        ],
        "venue": [
            ("paper", "paper_release", "paper_id"),
            ("paper_release", "release", "release_id"),
            ("release", "venue", "venue_id"),
        ],
        "release": [
            ("paper", "paper_release", "paper_id"),
            ("paper_release", "release", "release_id"),
        ],
    }

    def __init__(self, filename):
        self.db = Database(filename)
        self.papers_added = set()
        self.papers_excluded = set()

    def __contains__(self, paper: Paper):
        if paper in self.papers_excluded:
            return False
        elif paper in self.papers_added:
            return True
        else:
            return (
                self.db.select_id_from_values(
                    "paper",
                    "paper_id",
                    paper_id=self._find_paper_id(paper),
                    excluded=0,
                )
                is not None
            )

    def add(self, paper: Paper):
        if paper in self.papers_excluded:
            self.papers_excluded.remove(paper)
        self.papers_added.add(paper)

    def exclude(self, paper: Paper):
        if paper in self.papers_added:
            self.papers_added.remove(paper)
        self.papers_excluded.add(paper)

    def excludes(self, paper: Paper):
        return (
            paper in self.papers_excluded
            or self.db.select_id_from_values(
                "paper",
                "paper_id",
                paper_id=self._find_paper_id(paper),
                excluded=1,
            )
            is not None
        )

    def save(self):
        try:
            # Exclude papers.
            for paper in self.papers_excluded:
                self._create_paper_entry(paper, excluded=1)
            # Add or update papers.
            for paper in self.papers_added:
                self._save_paper(paper)
        except Exception as exc:
            raise RuntimeError(
                f"Error saving paper: {pprint.pformat(paper)}"
            ) from exc

    def _find_paper_id(self, paper: Paper):
        # Check paper IDs then title+abstract.
        for link_type in SOURCE_TYPES:
            paper_id = self.db.select_id_from_values(
                "paper_link",
                "paper_id",
                link_type=link_type,
                link=paper.get_ref(link_type),
            )
            if paper_id is not None:
                return paper_id
        return self.db.select_id_from_values(
            "paper", "paper_id", title=paper.title, abstract=paper.abstract
        )

    def _find_author_id(self, author: Author):
        # Check paper IDs then title+abstract.
        for link_type in SOURCE_TYPES:
            author_id = self.db.select_id_from_values(
                "author_link",
                "author_id",
                link_type=link_type,
                link=author.get_ref(link_type),
            )
            if author_id is not None:
                return author_id
        return self.db.select_id_from_values(
            "author", "author_id", author_name=author.name
        )

    def _create_paper_entry(self, paper: Paper, excluded: int = 0) -> int:
        paper_id = self._find_paper_id(paper) or self.db.insert(
            "paper",
            ("title", "abstract", "citation_count"),
            (paper.title, paper.abstract, paper.citation_count),
        )
        # Set excluded.
        self.db.modify(
            "UPDATE OR IGNORE paper SET excluded = ? WHERE paper_id = ?",
            (excluded, paper_id),
        )
        return paper_id

    def _save_paper(self, paper: Paper):
        db = self.db
        author_indices = []
        topic_indices = []
        # Paper: check MAG ID then title+abstract.
        paper_id = self._create_paper_entry(paper, excluded=0)
        # Links
        for link in paper.links:
            if not db.count(
                "paper_link",
                "paper_id",
                "link_type = ? AND link = ?",
                (link.type, link.ref),
            ):
                db.insert(
                    "paper_link",
                    ("paper_id", "link_type", "link"),
                    (paper_id, link.type, link.ref),
                )
        # Authors
        for author in paper.authors:
            # Author
            author_id = self._find_author_id(author) or db.insert(
                "author", ["author_name"], [author.name]
            )
            author_indices.append((author_id, author))
            # author links
            for author_link in author.links:
                db.modify(
                    "INSERT OR IGNORE INTO "
                    "author_link (author_id, link_type, link) VALUES(?, ?, ?)",
                    (author_id, author_link.type, author_link.ref),
                )
        # Venue
        venue = paper.venue
        if venue.name:
            venue_type = None
            venue_long_name = venue.name
            venue_name, venue_volume = get_venue_name_and_volume(
                venue_long_name
            )
            venue_id = db.select_id(
                "venue",
                "venue_id",
                "venue_type IS NULL and venue_name = ?",
                [venue_name],
            ) or db.insert(
                "venue", ("venue_type", "venue_name"), (venue_type, venue_name)
            )
            # Release
            (release,) = paper.releases
            release_date = None
            # NB: Even release.year may be None, so
            # we set it to an invalid year like -1 000 000,
            # as we don't expect humans to have written something in such year.
            release_year = int(release.year) if release.year else -1000000
            volume = venue_volume
            release_id = db.select_id_from_values(
                "release",
                "release_id",
                venue_id=venue_id,
                release_date=release_date,
                release_year=release_year,
                volume=volume,
            ) or db.insert(
                "release",
                ("venue_id", "release_date", "release_year", "volume"),
                (venue_id, release_date, release_year, volume),
            )
            # paper to release
            if not db.count(
                "paper_release",
                "paper_id",
                "paper_id = ? AND release_id = ?",
                (paper_id, release_id),
            ):
                db.insert(
                    "paper_release",
                    ("paper_id", "release_id"),
                    (paper_id, release_id),
                )
        # topics
        for topic in paper.topics:
            topic_id = db.select_id(
                "topic", "topic_id", "topic = ?", [topic.name]
            ) or db.insert("topic", ["topic"], [topic.name])
            topic_indices.append(topic_id)
        # paper to author
        for author_position, (author_id, author) in enumerate(author_indices):
            # Author affiliations may be empty, but we must still
            # save paper to author relation.
            for affiliation in author.affiliations or [""]:
                db.modify(
                    "INSERT OR IGNORE INTO paper_author "
                    "(paper_id, author_id, author_position, affiliation) "
                    "VALUES (?, ?, ?, ?)",
                    (paper_id, author_id, author_position, affiliation),
                )
        # paper to topic
        for topic_id in topic_indices:
            db.modify(
                "INSERT OR IGNORE INTO paper_topic "
                "(paper_id, topic_id) VALUES (?, ?)",
                (paper_id, topic_id),
            )

    def get_paper(self, paper_id) -> Optional[Paper]:
        """Return a Paper from given SQL paper ID."""
        row = self.db.query_one(
            "SELECT title, abstract, citation_count "
            "FROM paper WHERE paper_id = ?",
            [paper_id],
        )
        if row is None:
            return None

        paper = Paper(title=row[0], abstract=row[1], citation_count=row[2])

        authors = {}
        authors_pos = {}
        for r_author in self.db.query(
            "SELECT DISTINCT "
            "a.author_id, a.author_name, "
            "pa.author_position, pa.affiliation "
            "FROM paper_author AS pa "
            "JOIN author AS a "
            "ON pa.author_id = a.author_id "
            "WHERE pa.paper_id = ?",
            [paper_id],
        ):
            author_id = int(r_author[0])
            if author_id in authors:
                if r_author[3]:
                    authors[author_id].affiliations.append(r_author[3])
                assert authors_pos[author_id] == int(r_author[2])
            else:
                affiliations = [r_author[3]] if r_author[3] else []
                authors[author_id] = Author(
                    name=r_author[1], affiliations=affiliations
                )
                authors_pos[author_id] = int(r_author[2])
        for author_id, author in authors.items():
            author.links = [
                Link(type=r_alink[0], ref=r_alink[1])
                for r_alink in self.db.query(
                    "SELECT link_type, link FROM author_link WHERE author_id = ?",
                    [author_id],
                )
            ]
            author.aliases = [
                r_alias[0]
                for r_alias in self.db.query(
                    "SELECT alias FROM author_alias WHERE author_id = ?",
                    [author_id],
                )
            ]
            author.affiliations.extend(
                r_aff[0]
                for r_aff in self.db.query(
                    "SELECT DISTINCT affiliation FROM author_affiliation "
                    "WHERE author_id = ?",
                    [author_id],
                )
                if r_aff[0]
            )

        paper.authors = [
            authors[author_id]
            for _, author_id in sorted(
                (pos, aid) for aid, pos in authors_pos.items()
            )
        ]
        paper.releases = [
            Release(
                date=(
                    None
                    if r_release[0] is None
                    else self.db.timestamp_to_date(int(r_release[0]))
                ),
                year=int(r_release[1]),
                volume=r_release[2],
                venue=Venue(type=r_release[3], longname=r_release[4]),
            )
            for r_release in self.db.query(
                "SELECT DISTINCT "
                "r.release_date, r.release_year, r.volume, "
                "v.venue_type, v.venue_name "
                "FROM paper_release AS pr "
                "JOIN release AS r ON pr.release_id = r.release_id "
                "JOIN venue AS v ON r.venue_id = v.venue_id "
                "WHERE pr.paper_id = ?",
                [paper_id],
            )
        ]
        paper.topics = [
            Topic(name=r_topic[0])
            for r_topic in self.db.query(
                "SELECT DISTINCT t.topic FROM paper_topic AS pt "
                "JOIN topic AS t ON pt.topic_id = t.topic_id "
                "WHERE pt.paper_id = ?",
                [paper_id],
            )
        ]
        paper.links = [
            Link(type=row_link[0], ref=row_link[1])
            for row_link in self.db.query(
                "SELECT link_type, link FROM paper_link WHERE paper_id = ?",
                [paper_id],
            )
        ]

        return paper

    def query(
        self,
        *,
        paper_id: int = None,
        title: str = None,
        author: List[Union[str, int]] = None,
        words: str = None,
        keywords: List[str] = None,
        institution: str = None,
        venue: str = None,
        year: int = None,
        start: str = None,
        end: str = None,
        recent: bool = None,
        cited: bool = None,
        limit: int = None,
        offset: int = 0,
        verbose: bool = False,
    ) -> List[Paper]:
        # Use paper_id immediately if available
        if paper_id is not None:
            paper = self.get_paper(paper_id)
            if paper:
                yield paper
            return

        active_params = []
        if title and words:
            raise MutuallyExclusiveError("title", "words")
        elif title:
            active_params.append("title")
        elif words:
            active_params.append("words")
        if keywords:
            active_params.append("keywords")
        if author:
            active_params.append("author")
        if institution:
            active_params.append("institution")
        if venue:
            active_params.append("venue")
        if start is not None or end is not None:
            if year is not None:
                raise MutuallyExclusiveError("year", ("start", "end"))
            if start is not None:
                active_params.append("start")
            if end is not None:
                active_params.append("end")
        elif year is not None:
            active_params.append("year")
        if recent and cited:
            raise MutuallyExclusiveError("recent", "cited")
        elif recent:
            active_params.append("recent")
        elif cited:
            active_params.append("cited")

        shortener = Shortener()
        tables = []
        jointures = []
        seen_tables = set()
        seen_jointures = set()

        for key in active_params:
            for table in self.PARAM_TO_TABLES[key]:
                if table not in seen_tables:
                    seen_tables.add(table)
                    tables.append(table)

        if not tables:
            # No parameter passed. Nothing to return.
            return

        for table in tables:
            shortener.gen(table)
            for jointure in self.TABLE_TO_JOINTURES.get(table, ()):
                if jointure not in seen_jointures:
                    seen_jointures.add(jointure)
                    jointures.append(jointure)
                    shortener.gen(jointure[0])
                    shortener.gen(jointure[1])

        short_paper = shortener["paper"]
        where_clauses = []
        where_parameters = []
        if title is not None:
            where_clauses.append(f"lower({short_paper}.title) LIKE ?")
            where_parameters.append(f"%{title.lower()}%")
        if words is not None:
            param = f"%{words.lower()}%"
            where_clauses.append(
                f"(lower({short_paper}.title) LIKE ? OR lower({short_paper}.abstract) LIKE ?)"
            )
            where_parameters.extend((param, param))
        if keywords:
            short_topic = shortener["topic"]
            where_clauses.append(
                f"lower({short_topic}.topic) IN ({', '.join('?' * len(keywords))})"
            )
            where_parameters.extend(keywords)
        if author:
            author_names = [a.lower() for a in author if isinstance(a, str)]
            author_indices = [a for a in author if isinstance(a, int)]
            clauses = []
            if author_names:
                short_author = shortener["author"]
                clauses.append(
                    f"lower({short_author}.author_name) IN ({', '.join('?' * len(author_names))})"
                )
                where_parameters.extend(author_names)
            if author_indices:
                short_paper_author = shortener["paper_author"]
                clauses.append(
                    f"{short_paper_author}.author_id IN ({', '.join('?' * len(author_indices))})"
                )
                where_parameters.extend(author_indices)
            clause = " OR ".join(clauses)
            if len(clauses) > 1:
                clause = f"({clause})"
            where_clauses.append(clause)
        if institution:
            short_paper_author = shortener["paper_author"]
            where_clauses.append(
                f"lower({short_paper_author}.affiliation) LIKE ?"
            )
            where_parameters.append(f"%{institution.lower()}%")
        if venue:
            short_venue = shortener["venue"]
            where_clauses.append(f"lower({short_venue}.venue_name) LIKE ?")
            where_parameters.append(f"%{venue.lower()}%")
        if start is not None or end is not None:
            short_release = shortener["release"]
            clauses = []
            if start is not None:
                clauses.append(f"{short_release}.release_date >= ?")
                where_parameters.append(self.db.date_to_timestamp(start))
            if end is not None:
                clauses.append(f"{short_release}.release_date <= ?")
                where_parameters.append(self.db.date_to_timestamp(end))
            clause = " AND ".join(clauses)
            if len(clauses) > 1:
                clause = f"({clause})"
            where_clauses.append(clause)
        elif year is not None:
            short_release = shortener["release"]
            date_from = str(year).rjust(4, "0") + "-01-01"
            date_to = str(year).rjust(4, "0") + "-12-31"
            where_clauses.append(
                f"({short_release}.release_year = ? OR ({short_release}.release_date >= ? AND {short_release}.release_date <= ?))"
            )
            where_parameters.extend(
                (
                    year,
                    self.db.date_to_timestamp(date_from),
                    self.db.date_to_timestamp(date_to),
                )
            )

        pagination_clauses = []
        if recent:
            short_release = shortener["release"]
            pagination_clauses.append(
                f"ORDER BY {short_release}.release_year DESC, {short_release}.release_date DESC"
            )
        elif cited:
            pagination_clauses.append(
                f"ORDER BY {short_paper}.citation_count DESC"
            )
        if limit is not None:
            pagination_clauses.append(f"LIMIT {limit}")
            if offset is not None:
                pagination_clauses.append(f"OFFSET {offset}")

        joins = []
        for t1, t2, c in jointures:
            joins.append(
                f"JOIN {t2} AS {shortener[t2]} ON {shortener[t1]}.{c} = {shortener[t2]}.{c}"
            )

        query = f"SELECT DISTINCT {short_paper}.paper_id FROM paper AS {shortener['paper']} {' '.join(joins)}"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        if pagination_clauses:
            query += " " + " ".join(pagination_clauses)

        if verbose:
            print("[parameters]", ", ".join(active_params))
            print("[query]", query, where_parameters)

        rows = list(self.db.query(query, where_parameters))
        for i, row in enumerate(rows):
            if verbose:
                print(f"[paper {row[0]}] {i + 1}/{len(rows)}")
            yield self.get_paper(row[0])
