from datetime import datetime
from pathlib import Path
from time import sleep

import yaml
from serieux import CommentRec, deserialize, serialize

from paperoni.__main__ import Work
from paperoni.collection.filecoll import FileCollection
from paperoni.collection.memcoll import MemCollection
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import CollectionPaper
from paperoni.model.focus import Scored, Top
from paperoni.model.merge import PaperWorkingSet


def work(command, *, state_path: Path, collection_file: Path):
    Work(
        command=command,
        work_file=state_path,
        collection_file=collection_file,
        n=10,
    ).run()
    return deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state_path)


def test_work_get_does_not_duplicate(tmp_path: Path):
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    # update the max number of papers in the state to allow for more papers
    state.n = state.n * 2
    (tmp_path / "state.yaml").write_text(
        yaml.safe_dump(serialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state))
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    paper_keys = {pinfo.key for scored in state for pinfo in scored.value.collected}

    assert len(paper_keys) == len(state)

    mem_col = MemCollection()
    for paper in (scored.value.current for scored in state):
        assert mem_col.find_paper(paper) is None
        mem_col.add_papers([paper])


def test_work_get_does_not_duplicate_collection_papers(tmp_path: Path):
    work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )
    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    col = FileCollection(tmp_path / "collection.yaml")
    for paper in (scored.value.current for scored in state):
        assert col.find_paper(paper) is None


def test_work_updates_collection_papers(tmp_path: Path):
    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    # remove a link from a paper to fake an update on the next work-get
    paper_to_update: CollectionPaper = state.entries[2].value.current
    paper_to_update.links = paper_to_update.links[:-1]
    (tmp_path / "state.yaml").write_text(
        yaml.safe_dump(serialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state))
    )

    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    col = FileCollection(tmp_path / "collection.yaml")
    mem_col = MemCollection(_last_id=col._last_id)

    mem_col.add_papers([scored.value.current for scored in state])
    assert mem_col.find_paper(paper_to_update) is not None

    # At this point, if work-include is run, the paper should be updated in the
    # collection. Fake a concurrent update of the paper to discard the current
    # update inclusion
    assert col.find_paper(paper_to_update) is not None
    paper = CollectionPaper(**vars(col.find_paper(paper_to_update)))
    sleep(1)
    paper.version = datetime.now()
    col.add_papers([paper])

    work(
        Work.Include(),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    state = work(
        Work.Get(command=SemanticScholar().query),
        state_path=tmp_path / "state.yaml",
        collection_file=tmp_path / "collection.yaml",
    )

    col = FileCollection(tmp_path / "collection.yaml")
    mem_col = MemCollection(_last_id=col._last_id)
    mem_col.add_papers([scored.value.current for scored in state])
    assert mem_col.find_paper(paper_to_update) is not None
