import random
from dataclasses import dataclass

from giving import given

from paperoni.model import DatePrecision, PaperMerge
from paperoni.utils import (
    Doing,
    EquivalenceGroups,
    asciiify,
    associate,
    canonicalize_links,
    covguard,
    covguard_fn,
    extract_date,
    get_uuid_tag,
    is_canonical_uuid,
    similarity,
    squash_text,
    tag_uuid,
    url_to_id,
)


def test_asciiify():
    tests = {
        "Montréal": "Montreal",
        "Garçon": "Garcon",
    }
    for x, y in tests.items():
        assert asciiify(x) == y


def test_squash_text():
    tests = {
        "Montréal": "montreal",
        "Il était-une-fois un petit garçon...": "iletaitunefoisunpetitgarcon",
        "Bon    jour\ntoi": "bonjourtoi",
    }
    for x, y in tests.items():
        assert squash_text(x) == y


def test_extract_date():
    tests = {
        "Jan 06, 2023": (2023, 1, 6, DatePrecision.day),
        "Feb 3-7 2006": (2006, 2, 3, DatePrecision.day),
        "Feb 3-Mar 7 2006": (2006, 2, 3, DatePrecision.day),
        "8-15 April 1999": (1999, 4, 8, DatePrecision.day),
        "14 May 2001": (2001, 5, 14, DatePrecision.day),
        "June 2002": (2002, 6, 1, DatePrecision.month),
        "2002 June": (2002, 6, 1, DatePrecision.month),
        "2008 Jul 4": (2008, 7, 4, DatePrecision.day),
        2002: (2002, 1, 1, DatePrecision.year),
    }
    for date, (y, m, d, p) in tests.items():
        output = extract_date(date)
        assert output["date_precision"] == p
        date = output["date"]
        assert date.year == y
        assert date.month == m
        assert date.day == d


def test_extract_date_failures():
    assert extract_date("what is this?") is None


@dataclass(frozen=True)
class _Klass:
    ids: tuple[int]


def test_equivalence_group():
    eqv = EquivalenceGroups()

    eqv.equiv_all((1, 2, 7), cls=_Klass, under="A")
    eqv.equiv_all((3, 4), cls=_Klass, under="B")
    eqv.equiv_all((4, 5, 10), cls=_Klass, under="B")
    eqv.equiv_all((8, 9), cls=_Klass, under="A")
    eqv.equiv_all((), cls=_Klass, under="A")
    eqv.equiv_all((7, 8), cls=_Klass, under="A")

    a = _Klass(ids={1, 2, 7, 8, 9})
    b = _Klass(ids={3, 4, 5, 10})
    ab = list(eqv)

    assert ab == [a, b] or ab == [b, a]


test_links = [
    (
        True,
        ("arxiv", "1803.10225"),
        ("html", "https://arxiv.org/abs/1803.10225"),
    ),
    (
        True,
        ("arxiv", "1803.10225"),
        ("pdf", "https://arxiv.org/pdf/1803.10225.pdf"),
    ),
    (
        True,
        ("arxiv", "1803.10225"),
        ("html", "https://scirate.com/arxiv/1803.10225"),
    ),
    (
        True,
        ("openreview", "rCzfIruU5x5"),
        ("html", "https://openreview.net/forum?id=rCzfIruU5x5"),
    ),
    (
        True,
        ("openreview", "rCzfIruU5x5"),
        ("html", "https://www.openreview.net/forum?id=rCzfIruU5x5"),
    ),
    (
        True,
        ("dblp", "conf/emnlp/DongSCHC18"),
        (
            "html",
            "https://dblp.uni-trier.de/db/conf/emnlp/emnlp2018.html#DongSCHC18",
        ),
    ),
    (
        True,
        ("doi", "10.18653/v1/d18-1409"),
        ("html", "https://dx.doi.org/10.18653/v1/d18-1409"),
    ),
    (
        True,
        ("doi", "10.18653/v1/d18-1409"),
        ("html", "https://doi.org/10.18653/v1/d18-1409"),
    ),
    (
        None,
        ("html", "https://core.ac.uk/display/154983958"),
        ("html", "https://core.ac.uk/display/154983958"),
    ),
]


def test_url_to_id():
    for filt, expected, (_, url) in test_links:
        assert url_to_id(url) == (filt and expected)


def test_canonicalize_links():
    def to_dict(xy):
        x, y = xy
        return {"type": x, "link": y}

    results = canonicalize_links(
        [to_dict(given) for _, expected, given in test_links]
    )
    for _, expected, given in test_links:
        assert to_dict(expected) in results


def test_uuid_tagging():
    transient = bytes(bytearray.fromhex("32c90cf89d5a4d6a912d0041833912f5"))
    assert get_uuid_tag(transient) == "transient"
    assert not is_canonical_uuid(transient)

    canon = tag_uuid(transient, "canonical")
    assert canon == bytes(bytearray.fromhex("b2c90cf89d5a4d6a912d0041833912f5"))
    assert get_uuid_tag(canon) == "canonical"
    assert is_canonical_uuid(canon)

    transient = tag_uuid(canon, "transient")
    assert transient == bytes(
        bytearray.fromhex("32c90cf89d5a4d6a912d0041833912f5")
    )
    assert get_uuid_tag(transient) == "transient"
    assert not is_canonical_uuid(transient)


def test_similarity():
    assert similarity("bonjour", "bonjour") == 1
    assert similarity("bonjour", "bon-jour.") == 1


def test_similarity_2():
    assert similarity("Hugo Larochelle", "Marc Bellemare") < 0.5


def _test_permutations(tries, names1, transform=lambda x: x, extra=[], omit=0):
    random.seed(1234)
    print("Reference:", names1)
    for _ in range(tries):
        names2 = [transform(n1) for n1 in names1[omit:]] + extra
        random.shuffle(names2)
        print("Versus:", names2)
        results = associate(names1, names2)
        print("Results:", results)
        assert len(results) == len(names1) + len(extra)
        for i, j in results:
            if i is not None and j is not None:
                assert transform(names1[i]) == names2[j]


def test_associate_permutations():
    names = ["James Smith", "Annette Singalong", "Bob Yam", "Carole Nomnom"]
    _test_permutations(10, names)


def _initialify(name):
    first, last = name.split(" ")
    return f"{first[0]}. {last}"


def test_associate_initials():
    names = ["James Smith", "Annette Singalong", "Bob Yam", "Carole Nomnom"]
    _test_permutations(10, names, _initialify)


def test_associate_extra():
    names = ["James Smith", "Annette Singalong", "Bob Yam", "Carole Nomnom"]
    _test_permutations(10, names, _initialify, extra=["H. Boone"])


def test_associate_omit():
    names = ["James Smith", "Annette Singalong", "Bob Yam", "Carole Nomnom"]
    _test_permutations(10, names, _initialify, omit=1)


def test_associate_completely_different():
    names1 = ["James Smith", "Annette Singalong", "Bob Yam", "Carole Nomnom"]
    names2 = ["Oliver Kool", "Anne-Louise Lovelace"]
    assert len(associate(names1, names2)) == len(names1) + len(names2)


def test_associate_real_close():
    names1 = ["James Smith", "James Smeth"]
    names2 = ["James Smeth", "James Smith"]
    assert associate(names1, names2) == [(0, 1), (1, 0)]


def test_associate_real_close_initials():
    names1 = ["James Smith", "James Smeth"]
    names2 = ["J. Smeth", "J. Smith"]
    assert associate(names1, names2) == [(0, 1), (1, 0)]


def test_covguard():
    with given() as gv:
        gv.where(a=1, b=2, c=3).fail_if_empty()

        with Doing(a=1, b=2):
            with covguard(c=3):
                pass


def test_covguard_fn():
    @covguard_fn
    def f1(x):
        return x + 1

    @covguard_fn(x=5)
    def f2(y):
        return y + 2

    with given() as gv:
        gv.where(a=1).fail_if_empty()
        gv.where(a=2, x=5).fail_if_empty()

        with Doing(a=1):
            assert f1(4) == 5

        with Doing(a=2):
            assert f2(4) == 6
