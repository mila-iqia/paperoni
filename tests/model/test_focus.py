from pathlib import Path

import gifnoc
from pytest_regressions.data_regression import DataRegressionFixture
from serieux import CommentRec, deserialize, dump, serialize

from paperoni.__main__ import Work
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import Institution, Paper, PaperAuthor, PaperInfo
from paperoni.model.focus import Focus, Focuses, Scored, Top
from paperoni.model.merge import PaperWorkingSet
from tests.test_work import work


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


def test_score_non_ascii_title():
    focuses = Focuses(
        [
            Focus("author", "Alice Smith", 1.0),
            Focus("author", "Bob Jones", 0.5),
        ]
    )
    author = PaperAuthor(display_name="Alice Smith", author=None)
    paper = Paper(
        title="バイオディーゼル燃料【Powered by NICT】",
        authors=[author],
    )
    assert focuses.score(paper) == 0.0


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
    fst, snd = top_2
    assert fst.value.paper.title == "Paper from Charlie"
    assert snd.value.paper.title == "Paper from Alice"


def _top(n, key, elems):
    t = Top(n)
    t.add_all(Scored(key(x), x) for x in elems)
    return [x.value for x in t]


def test_top():
    strs = "This is a delightful string".split()
    assert _top(0, len, strs) == []
    assert _top(1, len, strs) == ["delightful"]
    assert _top(2, len, strs) == ["delightful", "string"]
    assert _top(3, len, strs) == ["delightful", "string", "This"]
    assert _top(4, len, strs) == ["delightful", "string", "This", "is"]
    assert _top(5, len, strs) == ["delightful", "string", "This", "is", "a"]


def test_top_incremental():
    ints = [5, 1, 4, 9, 13]
    t = Top(3)
    t.add_all(ints)
    assert list(t) == [13, 9, 5]
    t.add_all([12, -1])
    assert list(t) == [13, 12, 9]


def test_top_resort():
    strs = [Scored(len(x), x) for x in "This is a delightful string".split()]
    t = Top(3, strs)
    assert [x.value for x in t] == ["delightful", "string", "This"]
    strs[4].score = 150
    strs[4].value = "supercalifragilisticexpialidocious"
    t.resort()
    assert [x.value for x in t] == [
        "supercalifragilisticexpialidocious",
        "delightful",
        "This",
    ]


def test_serialization():
    strs = [Scored(len(x), x) for x in "This is a delightful string".split()]
    t = Top(3, strs)
    expected = {
        "n": 3,
        "entries": [
            {"score": 4.0, "value": "This"},
            {"score": 6.0, "value": "string"},
            {"score": 10.0, "value": "delightful"},
        ],
        "drop_zero": True,
    }
    assert serialize(Top[Scored[str]], t) == expected
    deser = deserialize(Top[Scored[str]], expected)
    assert isinstance(deser, Top)
    assert deser == t


def test_update(tmp_path: Path, data_regression: DataRegressionFixture):
    with gifnoc.overlay(
        {
            "paperoni.focuses": [
                "!institution :: Mila :: 10",
                "!author :: Irina Rish :: 3",
            ],
            "paperoni.autofocus": {
                "author": {"score": 1, "threshold": 5},
            },
        }
    ) as config:
        from paperoni.config import PaperoniConfig

        config: PaperoniConfig = config.paperoni

        state = work(
            Work.Get(command=SemanticScholar().query),
            work_file=tmp_path / "state.yaml",
            collection_file=tmp_path / "collection.yaml",
            n=100,
        )
        magnetoencephalography_paper: Scored[CommentRec[PaperWorkingSet, float]] = next(
            filter(
                lambda p: "artificial neural networks for magnetoencephalography".lower()
                in p.value.current.title.lower(),
                state,
            )
        )
        state.discard_all(state)
        state.add(magnetoencephalography_paper)
        dump(
            Top[Scored[CommentRec[PaperWorkingSet, float]]],
            state,
            dest=tmp_path / "state.yaml",
        )

        state = work(
            Work.Refine(),
            work_file=tmp_path / "state.yaml",
            collection_file=tmp_path / "collection.yaml",
        )
        magnetoencephalography_paper = next(iter(state))

        config.focuses.update(
            [magnetoencephalography_paper.value.current]
            * (config.autofocus.author.threshold - 1),
            config.autofocus,
        )

        # Nothing should change as we have passed the threshold for the authors
        # count affiliated to an institution
        assert len(config.focuses.focuses) == 2

        config.focuses.update(
            [magnetoencephalography_paper.value.current]
            * config.autofocus.author.threshold,
            config.autofocus,
        )

        assert len(config.focuses.focuses) > 2
        # Some of the author focus should have a score of config.autofocus.author.score
        assert any(
            f.type == "author" and f.score == config.autofocus.author.score
            for f in config.focuses.focuses
        )

        data_regression.check(serialize(Focuses, config.focuses))
