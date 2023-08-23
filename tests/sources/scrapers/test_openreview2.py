import coleo
import pytest
from giving import given
from pytest import fixture

from paperoni.model import Paper
from paperoni.sources.scrapers.openreview2 import (
    OpenReviewPaperScraper,
    OpenReviewProfileScraper,
    OpenReviewVenueScraper,
)

from .utils import controller_from_generator, isin


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


def test_query_title(scraper, data_regression):
    isin(
        data_regression,
        scraper.query(
            title=["Long-Term Rhythmic Video Soundtracker"],
            venue=["ICML.cc/2023/Conference"],
        ),
        basename="long_term",
        title="Long-Term Rhythmic Video Soundtracker",
    )


def test_query_author_id(scraper, data_regression):
    isin(
        data_regression,
        scraper.query(
            author_id=["~Jiashuo_Yu1"],
            venue=["ICML.cc/2023/Conference"],
        ),
        basename="long_term",
        title="Long-Term Rhythmic Video Soundtracker",
    )


profiles = [
    "~Yoshua_Bengio1",
    "~Aaron_Courville3",
    "~Yann_LeCun1",
    "~Adam_Klivans1",  # Has a lot of missing keys in the query data
    "~Animesh_Garg1",  # "" in a date
    "~Sheng_Zhong1",
]


@pytest.mark.parametrize(argnames=["name"], argvalues=[[x] for x in profiles])
def test_get_profile(name, pscraper, data_regression):
    (result,) = pscraper.query(name)
    data_regression.check(result.tagged_dict())


def test_prepare(scraper_p):
    @controller_from_generator
    def ctrl():
        a, p = yield
        while True:
            assert isinstance(p, Paper)
            a, p = yield "y" if len(a.name) % 2 else "n"

    with given() as gv:
        gv.display()

        with coleo.setvars(
            names=["Yoshua Bengio"],
            venue="ICML.cc/2023/Conference",
        ):
            auths = list(scraper_p.prepare(controller=ctrl))

        assert len(auths) == 1

        expected = {
            "Yoshua Bengio:openreview:~Yoshua_Bengio1",
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
    assert len(papers) > 20
    # OpenReview cross-indexes papers from DBLP, and we don't want to add those
    # because we get them from Semantic Scholar or other sources, so we check that
    # there are not too many results
    assert len(papers) < 200


def test_query_venues(vscraper, data_regression):
    confs = list(
        vscraper.query(
            pattern="iclr*conference",
        )
    )
    data_regression.check([x.tagged_dict() for x in confs])


def test_query_venues_neurips(vscraper, data_regression):
    confs = list(
        vscraper.query(
            pattern="neurips*conference",
        )
    )
    data_regression.check([x.tagged_dict() for x in confs])


def test_acquire_venues(vscraper, data_regression):
    with coleo.setvars(pattern="iclr*conference"):
        confs = list(vscraper.acquire())
    data_regression.check([x.tagged_dict() for x in confs])
    with vscraper.db as db:
        db.import_all(confs, history_file=False)
