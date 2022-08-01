import json
import re
from datetime import datetime

from coleo import Option, auto_cli, tooled, with_extras
from ovld import ovld
from sqlalchemy import select

from paperoni.db import schema as sch
from paperoni.db.database import Database
from paperoni.sources.model import AuthorMerge, PaperMerge

from .config import configure
from .sources.scrapers import load_scrapers
from .tools import EquivalenceGroups
from .utils import display


class ScraperWrapper:
    def __init__(self, name, scraper):
        self.name = name
        self.scraper = scraper
        self.__coleo_extras__ = [
            self.scraper.query,
            self.scraper.acquire,
            self.scraper.prepare,
        ]

    @tooled
    def query(self):
        load_config()

        for paper in self.scraper.query():
            print("=" * 80)
            display(paper)

    @tooled
    def acquire(self):
        pqs = generate_paper_queries()
        data = list(self.scraper.acquire(pqs))
        load_database(tag=f"acquire_{self.name}").import_all(data)

    @tooled
    def prepare(self):
        pas = generate_author_queries()
        data = list(self.scraper.prepare(pas))
        load_database(tag=f"prepare_{self.name}").import_all(data)


def query_scraper(scraper):
    @with_extras(scraper)
    def wrapped():
        load_config()

        for paper in scraper():
            print("=" * 80)
            display(paper)

    return wrapped


@tooled
def load_config(tag=None):
    # Configuration file
    config: Option = None

    return configure(config, tag=tag)


@tooled
def load_database(tag=None):
    config = load_config(tag=tag)
    return Database(config.database_file)


def generate_paper_queries():
    from sqlalchemy import select

    from paperoni.db import schema as sch
    from paperoni.sources import model as M

    with load_database() as db:
        q = select(sch.AuthorInstitution)
        queries = []
        for ai in db.session.execute(q):
            (ai,) = ai
            paper_query = M.AuthorPaperQuery(
                author=M.Author(
                    name=ai.author.name,
                    affiliations=[],
                    roles=[],
                    aliases=ai.author.aliases,
                    links=[
                        M.Link(
                            type=link.type,
                            link=link.link,
                        )
                        for link in ai.author.links
                    ],
                ),
                start_date=ai.start_date,
                end_date=ai.end_date,
            )
            queries.append(paper_query)

    return queries


def generate_author_queries():
    from sqlalchemy import select

    from paperoni.db import schema as sch
    from paperoni.sources import model as M

    with load_database() as db:
        q = select(sch.AuthorInstitution)
        authors = {}
        for ai in db.session.execute(q):
            (ai,) = ai
            authors[ai.author.author_id] = M.UniqueAuthor(
                author_id=ai.author_id,
                name=ai.author.name,
                affiliations=[],
                roles=[],
                aliases=ai.author.aliases,
                links=[
                    M.Link(
                        type=link.type,
                        link=link.link,
                    )
                    for link in ai.author.links
                ],
            )

    results = [author for author in authors.values()]
    return results


def replay():
    # History file to replay
    # [positional: *]
    history: Option = []

    # Lower bound
    after: Option = None

    # Upper bound
    before: Option = None

    load_database().replay(
        history=history,
        before=before,
        after=after,
    )


@ovld
def row_text(x: str):
    return x


@ovld
def row_text(x: bytes):
    return x.hex()


@ovld
def row_text(x: int):
    if x > 800000000:
        return datetime.fromtimestamp(x).strftime("%Y-%m-%d")
    else:
        return str(x)


@ovld
def row_text(x: object):
    return str(x)


def show_rows(rows, format):
    match format:
        case "plain":
            return show_rows(rows, ("plain", " "))
        case ("plain", delimiter):
            for row in rows:
                print(delimiter.join(row.values()))
        case "json":
            print(json.dumps(rows, indent=4))
        case "table":
            from rich.console import Console
            from rich.table import Table

            if not rows:
                return

            r0 = rows[0]

            table = Table()

            for k in r0.keys():
                table.add_column(k)

            for row in rows:
                table.add_row(*row.values())

            console = Console()
            console.print(table)
        case _:
            raise TypeError(f"Invalid format: {format}")


def date_syntax(query):
    def replacer(m):
        (date,) = m.groups()
        parts = [int(x) for x in date.split("-")]
        while len(parts) < 3:
            parts.append(1)
        return str(int(datetime(*parts).timestamp() - 100))

    query = re.sub(pattern="#([0-9-]+)", string=query, repl=replacer)

    return query


def sql():

    # SQL query to run
    # [positional]
    query: Option

    # JSON output
    # [option: --json]
    json_output: Option & bool = False

    # Plain text output
    plain: Option & bool = False

    # Delimiter for plain output
    delimiter: Option = None

    if delimiter is None:
        delimiter = " "
    else:
        plain = True

    assert not (
        json_output and plain
    ), "--json and --plain are mutually exclusive"

    query = date_syntax(query)

    with load_database() as db:
        results = [
            {k: row_text(v) for k, v in zip(row.keys(), row)}
            for row in db.session.execute(query)
        ]

    if plain:
        show_rows(results, ("plain", delimiter))
    if json_output:
        show_rows(results, "json")
    else:
        show_rows(results, "table")


class search:
    def paper():
        # Part of the title of the paper
        title: Option = ""

        # Author of the paper
        author: Option = ""

        with load_database() as db:
            stmt = select(sch.Paper)
            if title:
                stmt = stmt.filter(sch.Paper.title.like(f"%{title}%"))
            if author:
                stmt = (
                    stmt.join(sch.Paper.paper_author).join(
                        sch.PaperAuthor.author
                    )
                    # .join(sch.Author.author_alias)
                    # .join(sch.AuthorAlias.name.like(f"%{author}%"))
                    .filter(sch.Author.name.like(f"%{author}%"))
                )

            for (entry,) in db.session.execute(stmt):
                display(entry)
                print("=" * 80)


class merge:
    def author():
        with load_database(tag="merge") as db:
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
            eqv = EquivalenceGroups()
            names = {}
            for r in results:
                ids = {r[0], *r[1].split(";")}
                eqv.equiv_all(ids)
                for i in ids:
                    names[i] = r[2]

            merges = []
            for main, ids in eqv.groups().items():
                print(f"Merging {len(ids)} IDs for {names[main]}")
                merges.append(AuthorMerge(ids=ids))

        db.import_all(merges)

    def paper():
        with load_database(tag="merge") as db:
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
            eqv = EquivalenceGroups()
            names = {}
            for r in results:
                ids = {r[0], *r[1].split(";")}
                eqv.equiv_all(ids)
                for i in ids:
                    names[i] = r[2]

            merges = []
            for main, ids in eqv.groups().items():
                assert len(ids) > 1
                print(f"Merging {len(ids)} IDs for {names[main]}")
                merges.append(PaperMerge(ids=ids))

        db.import_all(merges)


scrapers = load_scrapers()

wrapped = {
    name: ScraperWrapper(name, scraper) for name, scraper in scrapers.items()
}

commands = {
    "query": {name: w.query for name, w in wrapped.items()},
    "acquire": {name: w.acquire for name, w in wrapped.items()},
    "prepare": {name: w.prepare for name, w in wrapped.items()},
    "replay": replay,
    "merge": merge,
    "search": search,
    "sql": sql,
}


def main():
    auto_cli(commands)
