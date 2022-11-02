import coleo
import pytest
from giving import given
from pytest import fixture

from paperoni.display import display
from paperoni.model import Paper
from paperoni.sources.scrapers.openreview import (
    OpenReviewPaperScraper,
    OpenReviewProfileScraper,
    OpenReviewVenueScraper,
)
from paperoni.tools import QueryError

from .utils import Artifacts, controller_from_generator


@fixture(scope="module")
def artifacts():
    return Artifacts("openreview_artifacts")


@fixture
def scraper(config_empty):
    return OpenReviewPaperScraper(config_empty, config_empty.database)


@fixture
def vscraper(config_empty):
    return OpenReviewVenueScraper(config_empty, config_empty.database)


@fixture
def pscraper(config_empty):
    return OpenReviewProfileScraper(config_empty, config_empty.database)


@fixture
def scraper_y(config_yoshua):
    return OpenReviewPaperScraper(config_yoshua, config_yoshua.database)


@fixture
def scraper_p(config_profs):
    return OpenReviewPaperScraper(config_profs, config_profs.database)


def test_query_title(scraper, artifacts):
    assert artifacts["discrete"].isin(
        scraper.query(
            title=["Discrete-Valued Neural Communication"],
            venue=["NeurIPS.cc/2021/Conference"],
        )
    )


def test_query_author(scraper, artifacts):
    assert artifacts["discrete"].isin(
        scraper.query(
            author=["Yoshua Bengio"],
            venue=["NeurIPS.cc/2021/Conference"],
        )
    )


def test_query_author_id(scraper, artifacts):
    assert artifacts["discrete"].isin(
        scraper.query(
            author_id=["~Yoshua_Bengio1"],
            venue=["NeurIPS.cc/2021/Conference"],
        )
    )


profiles = [
    "~Yoshua_Bengio1",
    "~Aaron_Courville3",
    "~Yann_LeCun1",
]


@pytest.mark.parametrize(argnames=["name"], argvalues=[[x] for x in profiles])
def test_get_profile(name, pscraper, artifacts):
    assert artifacts[name].isin(pscraper.query(name))


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
            names=["Yoshua Bengio", "Aaron Courville", "Doina Precup"],
            venue="NeurIPS.cc/2021/Conference",
        ):
            auths = list(scraper_p.prepare(controller=ctrl))

        assert len(auths) > 1

        expected = {
            "Doina Precup:!openreview:~Doina_Precup1",
            "Yoshua Bengio:openreview:~Yoshua_Bengio1",
            "Aaron Courville:openreview:~Aaron_Courville3",
        }

        lnks = {
            f"{auth.name}:{lnk.type}:{lnk.link}"
            for auth in auths
            for lnk in auth.links
        }
        print(lnks)
        assert expected & lnks == expected


def test_prepare_given(scraper_p):
    with coleo.setvars(given_id="1234567890", names=["Joelle Pineau"]):
        results = list(scraper_p.prepare(controller=lambda *_: "q"))
        assert len(results) == 1
        (jp,) = results
        assert jp.name == "Joelle Pineau"
        assert jp.links[0].type == "openreview"
        assert jp.links[0].link == "1234567890"


def test_acquire(scraper_y):
    papers = list(scraper_y.acquire())
    print(len(papers))
    assert len(papers) > 50
    # OpenReview cross-indexes papers from DBLP, and we don't want to add those
    # because we get them from Semantic Scholar or other sources, so we check that
    # there are not too many results
    assert len(papers) < 200


def test_query_venues(vscraper, artifacts):
    confs = list(
        vscraper.query(
            pattern="iclr*conference",
        )
    )
    assert artifacts["iclr2017"].isin(confs)
    assert artifacts["iclr2020"].isin(confs)
    assert artifacts["iclr2021"].isin(confs)


def test_query_venues_neurips(vscraper):
    confs = list(
        vscraper.query(
            pattern="neurips*conference",
        )
    )
    assert len(confs) >= 2


def test_acquire_venues(vscraper, artifacts):
    with coleo.setvars(pattern="iclr*conference"):
        confs = list(vscraper.acquire())
    assert artifacts["iclr2017"].isin(confs)
    assert artifacts["iclr2020"].isin(confs)
    assert artifacts["iclr2021"].isin(confs)
    with vscraper.db as db:
        db.import_all(confs, history_file=False)
