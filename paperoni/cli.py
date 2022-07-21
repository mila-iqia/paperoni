from coleo import Option, auto_cli, tooled, with_extras

from paperoni.db.database import Database

from .config import configure, scrapers
from .sources.scrapers import semantic_scholar
from .utils import display


class ScraperWrapper:
    def __init__(self, scraper):
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
        load_database(tag=f"acquire_{self.scraper.name}").import_all(data)

    @tooled
    def prepare(self):
        pas = generate_author_queries()
        data = list(self.scraper.prepare(pas))
        load_database(tag=f"prepare_{self.scraper.name}").import_all(data)


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
            authors[ai.author.author_id] = M.Author(
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

    results = [
        M.AuthorQuery(author_id=aid, author=author)
        for aid, author in authors.items()
    ]
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


wrapped = {name: ScraperWrapper(scraper) for name, scraper in scrapers.items()}


commands = {
    "query": {name: w.query for name, w in wrapped.items()},
    "acquire": {name: w.acquire for name, w in wrapped.items()},
    "prepare": {name: w.prepare for name, w in wrapped.items()},
    "replay": replay,
}


def main():
    auto_cli(commands)
