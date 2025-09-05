from functools import partial
from pathlib import Path

import yaml
from serieux import CommentRec, deserialize, serialize

from paperoni.__main__ import Work
from paperoni.collection.filecoll import FileCollection
from paperoni.collection.tmpcoll import TmpCollection
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import Paper
from paperoni.model.focus import Scored, Top
from paperoni.model.merge import PaperWorkingSet


def work(command, *, state_path: Path, collection_dir: Path):
    Work(command=command, work_file=state_path, collection_dir=collection_dir).run()
    return deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state_path)


def test_get_does_not_duplicate(tmp_path: Path):
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    # update the max number of papers in the state to allow for more papers
    state.n = state.n * 2
    (tmp_path / "state.yaml").write_text(
        yaml.safe_dump(serialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state))
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    paper_keys = {pinfo.key for scored in state for pinfo in scored.value.collected}

    assert len(paper_keys) == len(state)

    tmp_col = TmpCollection()
    for paper in (scored.value.current for scored in state):
        assert tmp_col.find_paper(paper) is None
        tmp_col.add_papers([paper])


def test_get_does_not_duplicate_collection_papers(tmp_path: Path):
    work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )
    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    col = FileCollection(tmp_path / "collection")
    for paper in (scored.value.current for scored in state):
        assert col.find_paper(paper) is None


def test_get_updates_collection_papers(tmp_path: Path):
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    # remove a link from a paper to fake an update
    paper_to_update: Paper = state.entries[2].value.current
    paper_to_update.links = paper_to_update.links[:-1]
    (tmp_path / "state.yaml").write_text(
        yaml.safe_dump(serialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state))
    )

    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    tmp_col = TmpCollection()
    tmp_col.add_papers([scored.value.current for scored in state])

    assert tmp_col.find_paper(paper_to_update) is not None

    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_dir=tmp_path / "collection",
    )

    tmp_col = TmpCollection()
    tmp_col.add_papers([scored.value.current for scored in state])

    assert tmp_col.find_paper(paper_to_update) is None
