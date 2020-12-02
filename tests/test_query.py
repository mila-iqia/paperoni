import re

from paperoni.papers import Papers

from .common import apikey, qm


def test_query_one(qm):
    papers = qm.query(
        {"author": "yoshua bengio", "words": "GAN",},
        attrs=",".join(Papers.fields),
        count=7,
        orderby="CC:desc",
    )
    papers = Papers({p["Id"]: p for p in papers})

    # Must be 7 papers
    assert len(papers) == 7

    # Most cited paper must be first
    cc = [p.citations for p in papers]
    assert list(sorted(cc, reverse=True)) == cc

    # Yoshua must be an author in all of them
    for p in papers:
        assert any(auth.name.lower() == "yoshua bengio" for auth in p.authors)

    # "GAN" must be a word in all papers
    for p in papers:
        assert re.findall(r"\bgan\b", p.title.lower()) or re.findall(
            r"\bgan\b", p.abstract.lower()
        )


def test_query_two(qm):
    papers = qm.query(
        {
            "keywords": ["artificial intelligence", "theoretical physics",],
            "title": "cosmic",
        },
        attrs=",".join(Papers.fields),
        orderby="D:desc",
    )
    papers = Papers({p["Id"]: p for p in papers})

    # Most recent paper must be first
    cc = [p.date for p in papers]
    assert list(sorted(cc, reverse=True)) == cc

    # "cosmic" must be a word in all titles
    for p in papers:
        assert re.findall(r"\bcosmic\b", p.title.lower())
