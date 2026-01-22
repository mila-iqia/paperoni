from datetime import datetime
from pathlib import Path
from time import sleep

from serieux import CommentRec, dump, load

from paperoni.__main__ import Work
from paperoni.collection.filecoll import FileCollection
from paperoni.collection.memcoll import MemCollection
from paperoni.discovery.semantic_scholar import SemanticScholar
from paperoni.model.classes import CollectionPaper
from paperoni.model.focus import Scored, Top
from paperoni.model.merge import PaperWorkingSet


async def work(command, **kwargs):
    work_file = kwargs.pop("work_file")
    cf = kwargs.pop("collection_file")
    await Work(
        command=Work.Configure(n=kwargs.pop("n", 10)),
        work_file=work_file,
        collection_file=cf,
        **kwargs,
    ).run()
    await Work(
        command=command,
        work_file=work_file,
        collection_file=cf,
        **kwargs,
    ).run()
    return load(Top[Scored[CommentRec[PaperWorkingSet, float]]], work_file)


async def test_work_get_does_not_duplicate(tmp_path: Path):
    state = await work(
        Work.Get(command=SemanticScholar().query),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    # update the max number of papers in the state to allow for more papers
    state.n = state.n * 2
    dump(
        Top[Scored[CommentRec[PaperWorkingSet, float]]],
        state,
        dest=tmp_path / "state.json",
    )

    state = await work(
        Work.Get(command=SemanticScholar().query),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    paper_keys = {pinfo.key for scored in state for pinfo in scored.value.collected}

    assert len(paper_keys) == len(state)

    mem_col = MemCollection()
    for paper in (scored.value.current for scored in state):
        assert await mem_col.find_paper(paper) is None
        await mem_col.add_papers([paper])


async def test_work_get_does_not_duplicate_collection_papers(tmp_path: Path):
    await work(
        Work.Get(command=SemanticScholar().query),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )
    await work(
        Work.Include(),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )
    state = await work(
        Work.Get(command=SemanticScholar().query),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    col = FileCollection(file=tmp_path / "collection.json")
    for paper in (scored.value.current for scored in state):
        assert await col.find_paper(paper) is None


async def test_work_updates_collection_papers(tmp_path: Path):
    state = await work(
        Work.Get(command=SemanticScholar().query),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    # remove a link from a paper to fake an update on the next work-get
    paper_to_update: CollectionPaper = state.entries[2].value.current
    paper_to_update.links = paper_to_update.links[:-1]
    dump(
        Top[Scored[CommentRec[PaperWorkingSet, float]]],
        state,
        dest=tmp_path / "state.json",
    )

    await work(
        Work.Include(),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    state = await work(
        Work.Get(command=SemanticScholar().query, check_paper_updates=True),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    col = FileCollection(file=tmp_path / "collection.json")
    mem_col = MemCollection(_last_id=col._last_id)

    await mem_col.add_papers([scored.value.current for scored in state])
    assert await mem_col.find_paper(paper_to_update) is not None

    # At this point, if work-include is run, the paper should be updated in the
    # collection. Fake a concurrent update of the paper to discard the current
    # update inclusion
    assert await col.find_paper(paper_to_update) is not None
    paper = CollectionPaper(**vars(await col.find_paper(paper_to_update)))
    sleep(1)
    paper.version = datetime.now()
    await col.add_papers([paper])

    await work(
        Work.Include(),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    state = await work(
        Work.Get(command=SemanticScholar().query, check_paper_updates=True),
        work_file=tmp_path / "state.json",
        collection_file=tmp_path / "collection.json",
    )

    col = FileCollection(file=tmp_path / "collection.json")
    mem_col = MemCollection(_last_id=col._last_id)
    await mem_col.add_papers([scored.value.current for scored in state])
    assert await mem_col.find_paper(paper_to_update) is not None
