import os

from coleo import Option, auto_cli, tooled, with_extras

from paperoni.db.database import Database

from .config import config as pconfig, configure, scrapers
from .sources.scrapers import semantic_scholar
from .utils import format_term_long as ft


@tooled
def search_interface(scraper):
    wow: Option = 3
    print(scraper, wow)


def wrap_scraper(scraper):
    @with_extras(scraper)
    def wrapped():
        for paper in scraper():
            print("=" * 80)
            ft(paper)

    return wrapped


def replay():
    # Configuration file
    config: Option = None

    # History file to replay
    history: Option = None

    if not config:
        config = os.getenv("PAPERONI_CONFIG")

    configure(config)

    Database(pconfig.database_file).replay(history_file=history)


commands = {
    "scrape": {
        name: wrap_scraper(scraper) for name, scraper in scrapers.items()
    },
    "replay": replay,
}


def main():
    auto_cli(commands)
