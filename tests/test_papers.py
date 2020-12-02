import textwrap

import pytest

from .common import (
    precollected,
    researcher,
    researchers,
    some_other_paper,
    some_paper,
)


def test_bibtex(some_paper):
    expected = textwrap.dedent(
        """
        @inproceedings{merrienboer2018-differentiation97,
            author = {Bart van Merrienboer and Olivier Breuleux and Arnaud Bergeron and Pascal Lamblin},
            title = {Automatic differentiation in ML: Where we are and where we should be going},
            year = {2018},
            booktitle = {Advances in Neural Information Processing Systems},
            pages = {8757-8767}
        }"""[
            1:
        ]
    )

    assert some_paper.bibtex() == expected


def test_shortcuts(some_paper):
    assert (
        some_paper.title
        == "Automatic differentiation in ML: Where we are and where we should be going"
    )
    assert some_paper.year == 2018
    assert (
        some_paper.venue == "Advances in Neural Information Processing Systems"
    )
    assert some_paper.conference == "neurips2018"


def test_authors(some_paper):
    auth = some_paper.authors
    assert len(auth) == 4
    me = auth[1]

    assert me.name == "Olivier Breuleux"
    assert me.role == {"old"}
    assert me.affiliations == ["Université de Montréal"]


def test_authors_2(some_other_paper):
    auth = some_other_paper.authors
    assert len(auth) == 3
    me = auth[0]

    assert me.name == "Olivier Breuleux"
    assert me.role == {"young"}
    assert me.affiliations == ["Université de Montréal"]


def test_query_author(precollected):
    name = "pascal vincent"
    results = precollected.query({"author": name})
    for result in results:
        assert any(auth.name.lower() == name for auth in result.authors)
    for paper in precollected:
        if paper not in results:
            assert all(auth.name.lower() != name for auth in paper.authors)
