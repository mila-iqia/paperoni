from paperoni.ext import sarc
from paperoni.model.classes import Author, Paper, PaperAuthor
from paperoni.operations import paper_map


def make_paper(email: str | None) -> Paper:
    return Paper(
        key="test",
        title="Deep Learning",
        authors=[
            PaperAuthor(
                author=Author(name="Yoshua Bengio", email=email),
                display_name="Yoshua Bengio",
            )
        ],
    )


def test_paper_map_preserves_author_email():
    # Regression test: paper_map used to rebuild Author without the email
    # field, silently nulling emails added manually or by an extension.
    p = make_paper("yoshua@mila.quebec")
    mapped = paper_map(p)
    assert mapped.authors[0].author.email == "yoshua@mila.quebec"


def test_associate_email_does_not_revert_manual_email():
    # Regression test: with no SARC match, associate_email must leave an
    # existing email untouched.
    old_map = sarc.MAP
    sarc.MAP = {}
    try:
        p = make_paper("yoshua@mila.quebec")
        result = sarc.associate_email(p)
        assert result.new.authors[0].author.email == "yoshua@mila.quebec"
        assert not result.changed
    finally:
        sarc.MAP = old_map
