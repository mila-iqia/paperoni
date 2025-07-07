from serieux import deserialize, serialize

from paperoni.model.classes import Institution, Paper, PaperAuthor, PaperInfo
from paperoni.model.focus import Focus, Focuses, Top


def test_focus_scoring():
    focuses = Focuses(
        [
            Focus("author", "Alice Smith", 1.0),
            Focus("author", "Bob Jones", 0.5),
            Focus("institution", "MIT", 2.0),
            Focus("institution", "Stanford", 1.5),
        ]
    )

    # Test author scoring
    author1 = PaperAuthor(display_name="Alice Smith", author=None)
    author2 = PaperAuthor(display_name="Bob Jones", author=None)
    author3 = PaperAuthor(display_name="Charlie Brown", author=None)

    assert focuses.score(author1) == 1.0
    assert focuses.score(author2) == 0.5
    assert focuses.score(author3) == 0.0

    # Test institution scoring
    mit_inst = Institution(name="MIT", category=None)
    stanford_inst = Institution(name="Stanford", category=None)
    harvard_inst = Institution(name="Harvard", category=None)

    author_with_mit = PaperAuthor(
        display_name="Unknown", author=None, affiliations=[mit_inst]
    )
    author_with_stanford = PaperAuthor(
        display_name="Unknown", author=None, affiliations=[stanford_inst]
    )
    author_with_harvard = PaperAuthor(
        display_name="Unknown", author=None, affiliations=[harvard_inst]
    )

    assert focuses.score(author_with_mit) == 2.0
    assert focuses.score(author_with_stanford) == 1.5
    assert focuses.score(author_with_harvard) == 0.0

    # Test combined scoring (author + institution)
    alice_at_mit = PaperAuthor(
        display_name="Alice Smith", author=None, affiliations=[mit_inst]
    )
    assert focuses.score(alice_at_mit) == 3.0  # 1.0 + 2.0

    # Test paper scoring
    paper = Paper(
        title="Test Paper",
        authors=[author1, author2, author3],
    )
    assert focuses.score(paper) == 1.5  # 1.0 + 0.5 + 0.0

    # Test paper info scoring
    paper_info = PaperInfo(paper=paper, key="xyz")
    assert focuses.score(paper_info) == 1.5


def test_focus_serialization():
    focus1 = Focus("author", "Alice Smith", 1.0, drive_discovery=False)
    focus2 = Focus("institution", "MIT", 2.0, drive_discovery=True)

    assert serialize(Focus, focus1) == "author::Alice Smith::1.0"
    assert serialize(Focus, focus2) == "!institution::MIT::2.0"

    assert deserialize(Focus, "author::Alice Smith::1.0") == focus1
    assert deserialize(Focus, "!institution::MIT::2.0") == focus2


def test_focuses_serialization():
    focus1 = Focus("author", "Alice Smith", 1.0, drive_discovery=False)
    focus2 = Focus("institution", "MIT", 2.0, drive_discovery=True)
    focuses = Focuses(focuses=[focus1, focus2])
    ser = ["author::Alice Smith::1.0", "!institution::MIT::2.0"]
    assert serialize(Focuses, focuses) == ser
    assert deserialize(Focuses, ser) == focuses


def test_focuses_top():
    focuses = Focuses(
        [
            Focus("author", "Alice", 1.0),
            Focus("author", "Bob", 0.5),
            Focus("author", "Charlie", 2.0),
        ]
    )

    papers = [
        PaperInfo(
            paper=Paper(
                title=f"Paper from {foc.name}",
                authors=[PaperAuthor(display_name=foc.name, author=None)],
            ),
            key="xyz",
        )
        for foc in focuses.focuses
    ]

    top_2 = focuses.top(papers, 2)
    assert len(top_2) == 2
    assert top_2[0].paper.title == "Paper from Charlie"
    assert top_2[1].paper.title == "Paper from Alice"


def _top(n, key, elems):
    t = Top(n=n, key=key)
    t.add_all(elems)
    return t


def test_top():
    strs = "This is a delightful string".split()
    assert _top(0, len, strs) == []
    assert _top(1, len, strs) == ["delightful"]
    assert _top(2, len, strs) == ["delightful", "string"]
    assert _top(3, len, strs) == ["delightful", "string", "This"]
    assert _top(4, len, strs) == ["delightful", "string", "This", "is"]
    assert _top(5, len, strs) == ["delightful", "string", "This", "is", "a"]


def test_top_incremental():
    strs = "This is a delightful string".split()
    t = _top(3, len, strs)
    assert t == ["delightful", "string", "This"]
    t.add_all(["footstool"])
    assert t == ["delightful", "footstool", "string"]


def test_top_resort():
    strs = [[x] for x in "This is a delightful string".split()]
    t = _top(3, (lambda x: len(x[0])), strs)
    assert t == [["delightful"], ["string"], ["This"]]
    t[1][0] = "supercalifragilisticexpialidocious"
    t.resort()
    assert t == [["supercalifragilisticexpialidocious"], ["delightful"], ["This"]]
