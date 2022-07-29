from collections import defaultdict

from coleo import Option, auto_cli, tooled, with_extras
from sqlalchemy import select

from paperoni.db import schema as sch
from paperoni.db.database import Database
from paperoni.sources.model import AuthorMerge, PaperMerge

from .config import configure
from .sources.scrapers import load_scrapers
from .tools import EquivalenceGroups, get_uuid_tag
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


class search:
    def paper():
        # Part of the title of the paper
        title: Option = ""

        # Author of the paper
        author: Option = ""

        with load_database() as db:
            stmt = select(sch.Paper).filter(sch.Paper.title.like(f"%{title}%"))
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
}


def main():
    auto_cli(commands)
