from pytest import fixture

from paperoni.sources.helpers import filter_researchers
from paperoni.sources.scrapers.base import BaseScraper


@fixture
def scraper_p(config_profs):
    return BaseScraper(config_profs, config_profs.database)


def test_author_queries(scraper_p):
    with scraper_p.db:
        auq = scraper_p.generate_author_queries()

    assert any(a.name == "Yoshua Bengio" for a in auq)

    names = {"Yoshua Bengio", "Aaron Courville", "Doina Precup"}
    auq = filter_researchers(
        auq,
        names=names,
    )
    assert {a.name for a in auq} == names

    auqb = filter_researchers(auq, before="Doina")
    assert {a.name for a in auqb} == {"Aaron Courville"}

    auqa = filter_researchers(auq, after="Doina")
    assert {a.name for a in auqa} == {"Yoshua Bengio"}

    auqx = filter_researchers(auq, after="a", before="z")
    assert {a.name for a in auqx} == {"Doina Precup", "Yoshua Bengio"}
