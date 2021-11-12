from coleo import Option, default, tooled

from ..papers2 import Paper
from .interactive import InteractiveCommands, default_commands
from .command_semantic_scholar import search
from ..sql.database import Database
from ..utils import get_venue_name_and_volume


class Collection:
    __slots__ = ("db", "papers_added", "papers_excluded")

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
            return self.db.select_id_from_values(
                "paper", "paper_id", title=paper.title, abstract=paper.abstract
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
        return paper in self.papers_excluded

    def save(self):
        # Delete excluded papers.
        for paper in self.papers_excluded:
            if paper.abstract is None:
                self.db.modify(
                    "DELETE FROM paper WHERE title = ? AND abstract IS NULL",
                    [paper.title],
                )
            else:
                self.db.modify(
                    "DELETE FROM paper WHERE title = ? AND abstract = ?",
                    (paper.title, paper.abstract),
                )
        # Add or update papers.
        for paper in self.papers_added:
            self._save_paper(paper)

    def _save_paper(self, paper: Paper):
        db = self.db
        author_indices = []
        topic_indices = []
        # Paper: check MAG ID then title+abstract.
        paper_id = (
            db.select_id_from_values(
                "paper_link",
                "paper_id",
                link_type="MAG",
                link=paper.get_ref("MAG"),
            )
            or db.select_id_from_values(
                "paper", "paper_id", title=paper.title, abstract=paper.abstract
            )
            or db.insert(
                "paper",
                ("title", "abstract", "citation_count"),
                (paper.title, paper.abstract, paper.citation_count),
            )
        )
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
            author_id = db.select_id(
                "author", "author_id", "author_name = ?", [author.name]
            ) or db.insert("author", ["author_name"], [author.name])
            author_indices.append((author_id, author))
            # author links
            for author_link in author.links:
                db.modify(
                    "INSERT OR IGNORE INTO "
                    "author_link (author_id, link_type, link) VALUES(?, ?, ?)",
                    (author_id, author_link.type, author_link.ref),
                )
            # Author affiliation.
            for affiliation in author.affiliations:
                # We don't have start and end date, so we check if
                # affiliation and role are already registered with null dates.
                if author.role is None:
                    count = db.count(
                        "author_affiliation",
                        "author_id",
                        "affiliation = ? AND role IS NULL "
                        "AND start_date IS NULL and end_date IS NULL",
                        [affiliation],
                    )
                else:
                    count = db.count(
                        "author_affiliation",
                        "author_id",
                        "affiliation = ? AND role = ? "
                        "AND start_date IS NULL and end_date IS NULL",
                        (affiliation, author.role),
                    )
                if not count:
                    db.insert(
                        "author_affiliation",
                        ("author_id", "affiliation", "role"),
                        (author_id, affiliation, author.role),
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
            release_year = int(release.year)
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
            for affiliation in author.affiliations:
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


search_commands = InteractiveCommands(
    "Include this paper in the collection?", default="y"
)


@search_commands.register("y", "[y]es")
def _y(self, paper, collection: Collection):
    """Include the paper in the collection"""
    collection.add(paper)
    return True


@search_commands.register("n", "[n]o")
def _n(self, paper, collection: Collection):
    """Exclude the paper from the collection"""
    collection.exclude(paper)
    return True


@search_commands.register("s", "[s]kip")
def _s(self, paper, collection: Collection):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


@tooled
def command_collect_semantic_scholar():
    """Collect papers from the Microsoft Academic database."""

    # File containing the collection
    # [alias: -c]
    collection: Option & Collection

    # Command to run on every paper
    command: Option = default(None)

    # Prompt for papers even if they were excluded from the collection
    show_excluded: Option & bool = default(False)

    # Display long form for each paper
    long: Option & bool = default(False)

    # Update existing papers with new information
    update: Option & bool = default(False)

    # Include all papers from the collection
    # [options: --yes]
    yes_: Option & bool = default(False)

    if yes_:
        command = "y"

    # Exclude all papers from the collection
    # [options: --no]
    no_: Option & bool = default(False)

    if no_:
        command = "n"

    papers = search()

    for paper in papers:
        if paper in collection:
            if update:
                collection.add(paper)
            continue
        if not show_excluded and collection.excludes(paper):
            continue
        instruction = search_commands.process_paper(
            paper,
            collection=collection,
            command=command,
            formatter=Paper.format_term_long if long else Paper.format_term,
        )
        if instruction is False:
            break

    collection.save()
