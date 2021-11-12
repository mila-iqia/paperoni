import json as json_module
import pprint

import tqdm
from coleo import Option, default, tooled

from paperoni.papers import Paper
from paperoni.sql.database import Database
from paperoni.utils import get_venue_name_and_volume


def _ms_has_author(data: dict, author: str):
    """Return True if Microsoft Academic paper data has given author."""
    return any(
        ms_author.get("DAuN", "").lower() == author
        or ms_author.get("AuN", "").lower() == author
        for ms_author in data.get("AA", [])
    )


def _ms_to_sql(data: dict, db: Database):
    """Save Microsoft Academic JSON data into SQLite database."""
    paper = Paper(data, None)
    author_indices = []
    topic_indices = []
    # Paper
    paper_id = db.select_id(
        "paper",
        "paper_id",
        "title = ? AND abstract = ?",
        (paper.title, paper.abstract),
    ) or db.insert(
        "paper", ("title", "abstract"), (paper.title, paper.abstract)
    )
    # MAG ID -> paper_link
    paper_link_type = "mag"
    paper_link = paper.pid
    if not db.count(
        "paper_link",
        "paper_id",
        "link_type = ? AND link = ?",
        (paper_link_type, paper_link),
    ):
        db.insert(
            "paper_link",
            ("paper_id", "link_type", "link"),
            (paper_id, paper_link_type, paper_link),
        )
    # Links
    for link in paper.links:
        if not db.count(
            "paper_link",
            "paper_id",
            "link_type = ? AND link = ?",
            (link.type, link.url),
        ):
            db.insert(
                "paper_link",
                ("paper_id", "link_type", "link"),
                (paper_id, link.type, link.url),
            )
    # Authors
    for author in paper.authors:
        # Author
        author_id = db.select_id(
            "author", "author_id", "author_name = ?", [author.name]
        ) or db.insert("author", ["author_name"], [author.name])
        author_indices.append((author_id, author))
        # author link
        link_type = "mag"
        link = author.aid
        db.modify(
            "INSERT OR IGNORE INTO "
            "author_link (author_id, link_type, link) VALUES(?, ?, ?)",
            (author_id, link_type, link),
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
    if paper.journal or paper.conference or paper.venue:
        if paper.journal:
            venue_type = "journal"
            venue_long_name = paper.journal
        elif paper.conference:
            venue_type = "conference"
            venue_long_name = paper.conference
        else:
            venue_type = None
            venue_long_name = paper.venue
        venue_name, venue_volume = get_venue_name_and_volume(venue_long_name)
        if venue_type is None:
            venue_id = db.select_id(
                "venue",
                "venue_id",
                "venue_type IS NULL and venue_name = ?",
                [venue_name],
            )
        else:
            venue_id = db.select_id(
                "venue",
                "venue_id",
                "venue_type = ? AND venue_name = ?",
                (venue_type, venue_name),
            )
        if venue_id is None:
            venue_id = db.insert(
                "venue", ("venue_type", "venue_name"), (venue_type, venue_name)
            )
        # Release
        release_date = db.date_to_timestamp(paper.date)
        release_year = int(paper.year)
        volume = data.get("V", None)
        if volume is None:
            volume = venue_volume
        elif venue_volume:
            volume = f"{venue_volume}, volume {volume}"
        if volume is None:
            release_id = db.select_id(
                "release",
                "release_id",
                "venue_id = ? AND release_date = ? AND release_year = ? AND volume IS NULL",
                (venue_id, release_date, release_year),
            )
        else:
            release_id = db.select_id(
                "release",
                "release_id",
                "venue_id = ? AND release_date = ? AND release_year = ? AND volume = ?",
                (venue_id, release_date, release_year, volume),
            )
        if release_id is None:
            release_id = db.insert(
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
    for topic in paper.keywords:
        topic_id = db.select_id(
            "topic", "topic_id", "topic = ?", [topic]
        ) or db.insert("topic", ["topic"], [topic])
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
        if not db.count(
            "paper_topic",
            "paper_id",
            "paper_id = ? AND topic_id = ?",
            (paper_id, topic_id),
        ):
            db.insert(
                "paper_topic", ("paper_id", "topic_id"), (paper_id, topic_id),
            )


def json_to_sql(data: dict, db: Database):
    try:
        _ms_to_sql(data, db)
    except Exception as exc:
        raise RuntimeError(
            f"Error converting paper: {pprint.pformat(data)}"
        ) from exc


@tooled
def command_import():
    """Import papers from JSON file to SQLite database."""

    # [alias: -v]
    # Verbose output
    verbose: Option & bool = default(False)

    # [group: json-to-sql]
    # [alias: -j]
    # JSON file to import
    json: Option
    # [group: json-to-sql]
    # [alias: -c]
    # SQLite database to export papers to
    collection: Option
    # [group: json-to-sql]
    # [alias: -a]
    # Import only papers from this author.
    # By default, all papers are imported.
    author: Option = default(None)

    with open(json) as file:
        ms_papers: dict = json_module.load(file)

    if author:
        author = author.lower()
        filtered_ms_papers = [
            paper
            for paper in ms_papers.values()
            if paper and _ms_has_author(paper, author)
        ]
    else:
        filtered_ms_papers = [paper for paper in ms_papers.values() if paper]

    if verbose:
        print(len(filtered_ms_papers), "selected paper(s).")

    db = Database(collection)

    for i, paper in tqdm.tqdm(
        enumerate(filtered_ms_papers), total=len(filtered_ms_papers)
    ):
        json_to_sql(paper, db)
