from dataclasses import dataclass

from serieux import deserialize, serialize
from serieux.features.comment import CommentRec

from paperoni.model.classes import (
    Author,
    Institution,
    InstitutionCategory,
    Link,
    PaperAuthor,
)
from paperoni.model.merge import merge, merge_all, qual, similarity


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Person:
    name: str
    job: str


def test_similarity():
    assert similarity("bonjour", "bonjour") == 1
    assert similarity("bon jour", "bon-jour.") == 1


def test_similarity_2():
    assert similarity("Hugo Larochelle", "Marc Bellemare") < 0.5


def test_augment():
    pt = Point(qual(3, 2.5), 4)
    ser = serialize(CommentRec[Point, float], pt)
    assert ser == {"x": {"$comment": 2.5, "$value": 3}, "y": 4}
    deser = deserialize(CommentRec[Point, float], ser)
    assert deser.x._ == 2.5


def test_merge_dicts():
    d1 = {"a": 1, "b": 2}
    d2 = {"c": 3}

    assert merge(d1, d2) == {"a": 1, "b": 2, "c": 3}
    assert merge(d1, qual(d2, -10)) == {"a": 1, "b": 2}
    assert merge(qual(d1, -10), d2) == {"c": 3}


def test_merge():
    p1 = Person(name=qual("John", 2), job="Carpenter")
    p2 = Person(name=qual("Johnny", 1), job=qual("Lawyer", 3))
    p12 = merge(p1, p2)
    assert p12 == Person(name="John", job="Lawyer")

    p3 = Person(name=qual("NO!", 1.5), job=qual("Philosopher", 4))
    p123 = merge(p12, p3)
    assert p123 == Person(name="John", job="Philosopher")

    p4 = qual(Person(name="Gunther", job="Unemployed"), 3)
    p34 = merge(p3, p4)
    assert p34 == Person(name="Gunther", job="Philosopher")


def test_merge_lists():
    p1 = Person(name="John", job="Carpenter")
    p2 = Person(name="John", job=qual("Lawyer", 3))
    p3 = qual(Person(name="Gunther", job="Unemployed"), 3)

    l1 = [p3, p1]
    l2 = [p2, p1]

    assert merge(l1, l2) == [p3, p1, p2]


def test_merge_lists_empty():
    l1 = [1, 2]
    l2 = []
    assert merge(l1, l2) == l1
    assert merge(l2, l1) == l1


def test_merge_author_lists():
    p1 = PaperAuthor(
        display_name="John",
        author=Author(name="John", links=[Link(type="job", link="baker")]),
    )
    p2 = PaperAuthor(
        display_name="John",
        author=Author(name="John", links=[Link(type="hair", link="yes")]),
    )
    p3 = qual(
        PaperAuthor(display_name="Gunther", author=Author(name="Gunther", links=[])), 3
    )

    l1 = [p3, p1]
    l2 = [p2]

    assert merge(l1, l2) == [
        PaperAuthor(display_name="Gunther", author=Author(name="Gunther", links=[])),
        PaperAuthor(
            display_name="John",
            author=Author(
                name="John",
                links=[Link(type="job", link="baker"), Link(type="hair", link="yes")],
            ),
        ),
    ]


def test_merge_author_lists_similarity():
    p1 = PaperAuthor(
        display_name="J. Smith",
        author=Author(name="J.", links=[Link(type="job", link="baker")]),
    )
    p2 = qual(
        PaperAuthor(
            display_name="John Smith",
            author=Author(name="John Smith", links=[Link(type="hair", link="yes")]),
        ),
        2,
    )
    p3 = qual(
        PaperAuthor(display_name="Gunther", author=Author(name="Gunther", links=[])), 3
    )

    l1 = [p3, p1]
    l2 = [p2]

    assert merge(l1, l2) == [
        PaperAuthor(display_name="Gunther", author=Author(name="Gunther", links=[])),
        PaperAuthor(
            display_name="John Smith",
            author=Author(
                name="John Smith",
                links=[Link(type="hair", link="yes"), Link(type="job", link="baker")],
            ),
        ),
    ]


def test_merge_institution_lists():
    i1 = Institution(name="MIT")
    i2 = qual(Institution(name="MIT", category=InstitutionCategory.academia), 2)
    i3 = qual(Institution(name="Stanford University"), 3)

    l1 = [i3, i1]
    l2 = [i2]

    merged = merge(l1, l2)
    assert merged == [
        Institution(name="Stanford University"),
        Institution(name="MIT", category=InstitutionCategory.academia),
    ]


def test_merge_all():
    ab = {"a": 1, "b": 2}
    c = {"c": 3}
    d = {"d": 4}
    assert merge_all([]) is None
    assert merge_all([ab]) == ab
    assert merge_all([c, ab, d]) == ab | c | d
