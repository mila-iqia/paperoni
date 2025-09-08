from functools import partial
from pathlib import Path

import yaml
from serieux import CommentRec, deserialize, serialize

from paperoni.__main__ import Work
from paperoni.collection.tmpcoll import TmpCollection
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.focus import Scored, Top
from paperoni.model.merge import PaperWorkingSet


def test_get_does_not_duplicate(tmp_path: Path):
    def patch_work(state_path: Path, author: str):
        command = Work(
            n=10,
            work_file=state_path,
            collection_dir=tmp_path,
            command=Work.Get(
                command=partial(
                    SemanticScholar().query,
                    author=author,
                )
            ),
        )
        command.run()
        return deserialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state_path)

    state = patch_work(tmp_path / "state.yaml", "Yoshua Bengio")
    # update the max number of papers in the state to allow for more papers
    state.n = state.n * 2
    (tmp_path / "state.yaml").write_text(
        yaml.safe_dump(serialize(Top[Scored[CommentRec[PaperWorkingSet, float]]], state))
    )

    state = patch_work(tmp_path / "state.yaml", "Yoshua Bengio")

    paper_keys = {pinfo.key for scored in state for pinfo in scored.value.collected}

    assert len(paper_keys) == len(state)

    tmp_col = TmpCollection()
    for paper in (scored.value.current for scored in state):
        assert tmp_col.find_paper(paper) is None
        tmp_col.add_papers([paper])
