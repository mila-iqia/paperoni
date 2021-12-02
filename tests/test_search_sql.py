import pytest
from paperoni.sql.collection import MutuallyExclusiveError
from paperoni.sql.collection import Collection


def _query(**kwargs):
    collection = Collection("tests/mila-papers.db")
    return list(collection.query(**kwargs))


def test_paper_id():
    # Currently paper_id must be paper ID field in SQL database.
    results = _query(paper_id=-1)
    assert results == []
    results = _query(paper_id=1)
    assert len(results) == 1


def test_title():
    results = _query(title="deep learning")
    assert len(results) == 82


def test_author():
    results = _query(author=["yoshua bengio"])
    assert len(results) == 593


def test_words():
    results = _query(words="machine learning")
    assert len(results) == 286


def test_keywords():
    results = _query(keywords=["deep learning"])
    assert len(results) == 296
    results = _query(keywords=["deep learning", "machine learning"])
    assert len(results) == 748


def test_institution():
    results = _query(institution="université de montréal")
    assert len(results) == 812
    results = _query(institution="mcgill")
    assert len(results) == 845


def test_venue():
    results = _query(venue="nature")
    assert len(results) == 38


def test_year():
    results = _query(year=2015)
    assert len(results) == 79


def test_start():
    results = _query(start="2019-10-01")
    assert len(results) == 1693


def test_end():
    results = _query(end="2020-12-15")
    assert len(results) == 1989


def test_start_end():
    results = _query(start="2019-10-01", end="2020-12-15")
    assert len(results) == 989


def test_recent():
    results = _query(recent=True)
    assert len(results) == 2692


def test_cited():
    results = _query(cited=True)
    assert len(results) == 2888


def test_limit():
    results = _query(author=["yoshua bengio"], limit=123)
    assert len(results) == 123


def test_offset():
    results = _query(author=["yoshua bengio"], limit=244, offset=39)
    assert len(results) == 244


def test_mutually_exclusive():
    with pytest.raises(MutuallyExclusiveError):
        _query(title="title", words="word")
    with pytest.raises(MutuallyExclusiveError):
        _query(year=1, start=1)
    with pytest.raises(MutuallyExclusiveError):
        _query(year=1, end=1)
    with pytest.raises(MutuallyExclusiveError):
        _query(recent=True, cited=True)
