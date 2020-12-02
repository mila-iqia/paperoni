import pytest

from paperoni.researchers import Role

from .common import (
    precollected,
    researcher,
    researchers,
    some_other_paper,
    some_paper,
)


def test_researcher_identity(researcher, some_paper, some_other_paper):
    rsch = researcher
    me1 = some_paper.authors[1]
    me2 = some_other_paper.authors[0]
    assert me1.researcher is rsch
    assert me2.researcher is rsch


def test_listed(some_other_paper):
    assert some_other_paper.authors[0].researcher.listed
    assert not some_other_paper.authors[1].researcher.listed
    assert not some_other_paper.authors[2].researcher.listed


def test_roles_at(researcher):
    rsch = researcher
    assert rsch.roles_at("1990-06-08") == []
    assert rsch.roles_at("2000-01-01") == [
        Role(status="young", begin="2000-01-01", end="2015-01-01")
    ]
    assert rsch.roles_at("2015-01-01") == [
        Role(status="young", begin="2000-01-01", end="2015-01-01"),
        Role(status="old", begin="2015-01-01", end=None),
    ]
    assert rsch.roles_at("2050-01-01") == [
        Role(status="old", begin="2015-01-01", end=None)
    ]


def test_status_at(researcher):
    rsch = researcher
    assert rsch.status_at("1990-06-08") == set()
    assert rsch.status_at("2000-01-01") == {"young"}
    assert rsch.status_at("2015-01-01") == {"young", "old"}
    assert rsch.status_at("2050-01-01") == {"old"}


def test_with_status(researcher):
    rsch = researcher
    assert rsch.with_status("young") == [
        Role(status="young", begin="2000-01-01", end="2015-01-01")
    ]
    assert rsch.with_status("dumdum") == []

    assert rsch.with_status("old", "young") == [
        Role(status="young", begin="2000-01-01", end="2015-01-01"),
        Role(status="old", begin="2015-01-01", end=None),
    ]
    assert rsch.with_status() == [
        Role(status="young", begin="2000-01-01", end="2015-01-01"),
        Role(status="old", begin="2015-01-01", end=None),
    ]
