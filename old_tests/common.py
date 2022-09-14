import os

import pytest


@pytest.fixture
def researchers():
    from paperoni.io import ResearchersFile

    here = os.path.dirname(__file__)
    return ResearchersFile(os.path.join(here, "rsch.json"))


@pytest.fixture
def researcher(researchers):
    return researchers.get("olivier breuleux")


@pytest.fixture
def precollected(researchers):
    from paperoni.io import PapersFile

    here = os.path.dirname(__file__)
    return PapersFile(os.path.join(here, "oli.json"), researchers=researchers)


@pytest.fixture
def some_paper(precollected):
    results = precollected.query(
        {
            "title": "Automatic differentiation in ML: Where we are and where we should be going",
            "venue": "NeurIPS",
        }
    )
    assert len(results) == 1
    return results[0]


@pytest.fixture
def some_other_paper(precollected):
    results = precollected.query(
        {
            "title": " Quickly generating representative samples from an rbm-derived process",
        }
    )
    assert len(results) == 1
    return results[0]


@pytest.fixture
def apikey():
    key = os.getenv("PAPERONI_API_KEY")
    if key is None:
        raise Exception("$PAPERONI_API_KEY must be set to execute test")
    return key


@pytest.fixture
def qm(apikey):
    from paperoni.query import QueryManager

    return QueryManager(apikey)
