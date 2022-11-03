import coleo
import pytest
from giving import given
from pytest import fixture

from paperoni.model import Paper
from paperoni.sources.scrapers.semantic_scholar import SemanticScholarScraper
from paperoni.tools import QueryError

from .utils import controller_from_generator, isin


@fixture
def scraper(config_empty):
    return SemanticScholarScraper(config_empty, config_empty.database)


@fixture
def scraper_y(config_yoshua):
    return SemanticScholarScraper(config_yoshua, config_yoshua.database)


@fixture
def scraper_p(config_profs):
    return SemanticScholarScraper(config_profs, config_profs.database)


def test_query_title(scraper, data_regression):
    isin(
        data_regression,
        scraper.query(title=["automatic differentiation in ml where we are"]),
        basename="autodiff_in_ml",
        ignore=["citation_count"],
        title="Automatic differentiation in ML: Where we are and where we should be going",
    )


def test_query_author(scraper, data_regression):
    isin(
        data_regression,
        scraper.query(title=["automatic differentiation in ml where we are"]),
        basename="autodiff_in_ml",
        ignore=["citation_count"],
        title="Automatic differentiation in ML: Where we are and where we should be going",
    )


def test_query_author_title(scraper):
    with pytest.raises(QueryError):
        list(
            scraper.query(
                author=["Olivier Breuleux"],
                title=["automatic differentiation in ml where we are"],
            )
        )


def test_prepare(scraper_p):
    @controller_from_generator
    def ctrl():
        a, p = yield
        while True:
            assert isinstance(p, Paper)
            a, p = yield "y" if len(a.name) % 2 else "n"

    with given() as gv:
        gv.display()

        # Verify that none of the authors has 1 or less papers
        gv["npapers"].filter(lambda n: n <= 1).fail()

        # Verify that common articles have been found
        gv["common"].filter(len).fail_if_empty()

        with coleo.setvars(
            names=["Yoshua Bengio", "Aaron Courville", "Doina Precup"]
        ):
            auths = list(scraper_p.prepare(controller=ctrl))

        assert len(auths) > 1

        expected = {
            "Aaron Courville:semantic_scholar:1760871",
            "Aaron Courville:semantic_scholar:2058336670",
            "Doina Precup:!semantic_scholar:144368601",
            # "Doina Precup:!semantic_scholar:115325970",
            "Yoshua Bengio:semantic_scholar:1751762",
            "Yoshua Bengio:semantic_scholar:1865800402",
            # "Yoshua Bengio:semantic_scholar:2163344329",
            # "Yoshua Bengio:semantic_scholar:146317558",
        }

        lnks = {
            f"{auth.name}:{lnk.type}:{lnk.link}"
            for auth in auths
            for lnk in auth.links
        }
        assert expected & lnks == expected


def test_prepare_given(scraper_p):
    with coleo.setvars(given_id="1234567890", names=["Joelle Pineau"]):
        results = list(scraper_p.prepare(controller=lambda *_: "q"))
        assert len(results) == 1
        (jp,) = results
        assert jp.name == "Joelle Pineau"
        assert jp.links[0].type == "semantic_scholar"
        assert jp.links[0].link == "1234567890"


def test_prepare_commands(scraper_p):
    @controller_from_generator
    def ctrl():
        yield
        yield "m"
        yield "m"
        a1, _ = yield "s"
        a2, _ = yield "d"
        assert a1.name != a2.name
        yield "q"
        assert False, "q should terminate"

    with given() as gv:
        gv.display()
        list(scraper_p.prepare(controller=ctrl))


def test_prepare_and_commit(scraper_p):
    @controller_from_generator
    def ctrl1():
        yield
        while True:
            yield "y"
            yield "n"

    @controller_from_generator
    def ctrl2():
        yield
        raise Exception("We are supposed to have processed all ids previously")

    with given() as gv:
        gv.display()

        with coleo.setvars(names=["Blake Richards"]):
            auths = list(scraper_p.prepare(controller=ctrl1))
            assert len(auths) > 1

        with scraper_p.db as db:
            # Commit all of our work
            db.import_all(auths, history_file=False)

        # We should be skipping all ids because we already have them
        with coleo.setvars(names=["Blake Richards"]):
            auths = list(scraper_p.prepare(controller=ctrl2))
            assert len(auths) == 0


def test_acquire(scraper_y):
    papers = list(scraper_y.acquire())
    print(len(papers))
    assert len(papers) > 900
