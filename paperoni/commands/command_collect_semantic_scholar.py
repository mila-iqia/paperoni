import pprint
from coleo import Option, default, tooled

from ..papers2 import Paper, Author
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
                "paper",
                "paper_id",
                paper_id=self._find_paper_id(paper),
                excluded=0
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
        return paper in self.papers_excluded or self.db.select_id_from_values(
            "paper",
            "paper_id",
            paper_id=self._find_paper_id(paper),
            excluded=1,
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
            raise RuntimeError(f"Error saving paper: {pprint.pformat(paper)}") from exc

    def _find_paper_id(self, paper: Paper):
        # Check paper IDs then title+abstract.
        for link_type in (
            "SemanticScholar",
            "MAG",
            "ACL",
            "DBLP",
            "DOI",
            "PubMed",
            "PubMedCentral",
        ):
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
        for link_type in (
            "SemanticScholar",
            "MAG",
            "ACL",
            "DBLP",
            "DOI",
            "PubMed",
            "PubMedCentral",
        ):
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
        paper_id = (
            self._find_paper_id(paper)
            or self.db.insert(
                "paper",
                ("title", "abstract", "citation_count"),
                (paper.title, paper.abstract, paper.citation_count),
            )
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
            author_id = self._find_author_id(author) or db.insert("author", ["author_name"], [author.name])
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
