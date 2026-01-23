import copy
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Generator

import gifnoc
import pytest
from easy_oauth.testing.utils import AppTester
from ovld import ovld
from serieux import serialize

from paperoni.collection.abc import PaperCollection, _id_types
from paperoni.collection.filecoll import FileCollection
from paperoni.collection.memcoll import MemCollection
from paperoni.collection.mongocoll import MongoCollection
from paperoni.collection.remotecoll import RemoteCollection
from paperoni.discovery.jmlr import JMLR
from paperoni.model.classes import (
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperInfo,
)

# There's a 1 paper overlap between the papers of Hugo Larochelle and Pascal Vincent
# There's no overlap between the papers of Guillaume Alain and the other two
AUTHORS_WITH_FAKE_INSTITUTION = ["Hugo Larochelle", "Pascal Vincent", "Guillaume Alain"]


@ovld
def eq(a: list, b: list):
    return len(a) == len(b) and all(eq(a, b) for a, b in zip(a, b))


@ovld
def eq(a: object, b: object):
    try:
        fields_a = vars(a)
        fields_b = vars(b)
        return eq(fields_a, fields_b)
    except TypeError:
        return (a is None) or (b is None) or a == b


@ovld
def eq(a: dict, b: dict):
    for k in set(a) & set(b):
        if not eq(a[k], b[k]):
            return False
    return True


async def _get_sample_papers():
    discoverer = JMLR()

    volumes: list[str] = []
    for volume in sorted(
        [v async for v in discoverer.list_volumes()], key=lambda x: int(x.lstrip("v"))
    ):
        if volume == "v25":
            break
        volumes.append(volume)

    papers: list[PaperInfo] = []
    for volume in volumes:
        async for p in discoverer.query(volume=volume, name="Yoshua Bengio"):
            papers.append(p)

    return papers


@pytest.fixture(scope="session")
async def sample_papers() -> Generator[list[Paper], None, None]:
    papers = await _get_sample_papers()

    papers: list[Paper] = sorted((p.paper for p in papers), key=lambda x: x.title)[:10]
    assert len(papers) == 10

    # Add fake institution to the papers
    for p in papers:
        for a in p.authors:
            if a.display_name in AUTHORS_WITH_FAKE_INSTITUTION:
                a.affiliations.extend(
                    [
                        Institution(name="MILA", category=InstitutionCategory.academia),
                        Institution(
                            name=f"{a.display_name} Uni",
                            category=InstitutionCategory.academia,
                        ),
                    ]
                )

    papers[0].flags = {"valid"}
    papers[1].flags = {"invalid"}
    papers[2].flags = {"valid", "invalid"}
    papers[3].flags = {"reviewed"}
    papers[4].flags = {"valid", "reviewed"}

    yield papers


@pytest.fixture(scope="session")
def sample_paper(sample_papers: list[Paper]) -> Generator[Paper, None, None]:
    yield sample_papers[len(sample_papers) // 2]


@pytest.fixture(scope="session")
def excluded_papers(
    sample_papers: list[Paper],
) -> Generator[list[Paper], None, None]:
    # add supported exclusion link types to the last 2 papers
    sample_papers = copy.deepcopy(sample_papers)
    papers = sample_papers[-2:]
    for p in papers:
        for lnk_type in _id_types:
            p.links.append(Link(type=lnk_type, link=f"test_{lnk_type}_{p.title}"))

    yield papers


@contextmanager
def _wrap(cfg_src: list[str | dict]):
    # This needs to run in the thread to reapply the configurations
    with gifnoc.use(*cfg_src):
        yield


@pytest.fixture(scope="module")
def app_coll(oauth_mock, cfg_src, sample_papers):
    from paperoni.web import create_app

    memcol = MemCollection()
    memcol._add_papers(sample_papers)
    memcol = serialize(MemCollection, memcol)

    memcol["$class"] = "paperoni.collection.memcoll:MemCollection"
    overrides = {
        "paperoni.collection": memcol,
        "paperoni.server.max_results": 5,
        "paperoni.server.auth.capabilities.guest_capabilities": ["search"],
    }

    cfg = [*cfg_src, overrides]

    with gifnoc.use(*cfg):
        with AppTester(
            create_app(), oauth_mock, port=18888, wrap=partial(_wrap, cfg)
        ) as appt:
            yield appt


@ovld
async def make_collection(t: type[MemCollection], tmp_path: Path):
    return MemCollection()


@ovld
async def make_collection(t: type[FileCollection], tmp_path: Path):
    return FileCollection(file=tmp_path / "collection.json")


@ovld
async def make_collection(t: type[MongoCollection], tmp_path: Path):
    mongo_collection = MongoCollection(database=tmp_path.name)
    await mongo_collection._ensure_connection()
    await mongo_collection._client.drop_database(mongo_collection.database)
    return mongo_collection


@ovld
async def make_collection(t: type[RemoteCollection], tmp_path: Path):
    class _RemoteCollection(RemoteCollection):
        async def add_papers(self, papers):
            pass

    return _RemoteCollection(endpoint="http://localhost:18888/api/v1")


@pytest.fixture(params=[MemCollection, FileCollection, MongoCollection])
async def collection(request, tmp_path: Path):
    yield await make_collection(request.param, tmp_path)


@pytest.fixture(params=[MemCollection, FileCollection, MongoCollection, RemoteCollection])
async def collection_r(request, tmp_path: Path, app_coll):
    yield await make_collection(request.param, tmp_path)


async def test_add_papers(collection: PaperCollection, sample_papers: list[Paper]):
    """Test adding multiple papers."""
    await collection.add_papers(sample_papers)

    assert eq([p async for p in collection.search()], sample_papers)


async def test_drop_collection(collection: PaperCollection, sample_papers: list[Paper]):
    """Test dropping a collection."""
    await collection.add_papers(sample_papers)

    await collection.drop()

    assert not [p async for p in collection.search()]


async def test_exclude_papers_multiple(
    collection: PaperCollection,
    sample_papers: list[Paper],
    excluded_papers: list[Paper],
):
    """Test excluding multiple papers."""
    await collection.exclude_papers(excluded_papers)

    await collection.add_papers(sample_papers)

    for excluded_paper in excluded_papers:
        assert not [p async for p in collection.search(title=excluded_paper.title)]


async def test_exclude_papers_unknown_link_type(collection: PaperCollection):
    """Test excluding papers with unknown link types."""
    paper = Paper(
        title="Unknown Links",
        links=[
            Link(type="unknown", link="some-link"),
        ],
    )
    await collection.exclude_papers([paper])

    await collection.add_papers([paper])

    assert eq([p async for p in collection.search()], [paper])


async def test_find_paper_by_link(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test finding a paper by its link."""
    await collection.add_papers(sample_papers)

    # Create a paper with a matching link
    search_paper = Paper(title="Search Paper by Link", links=sample_paper.links[0:1])
    found = await collection.find_paper(search_paper)

    assert eq(found, sample_paper)


async def test_find_paper_by_title(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test finding a paper by its title."""
    await collection.add_papers(sample_papers)

    # Create a paper with a matching title but no matching links
    search_paper = Paper(title=sample_paper.title, authors=sample_paper.authors)
    found = await collection.find_paper(search_paper)

    assert eq(found, sample_paper)


async def test_find_paper_not_found(
    collection: PaperCollection, sample_papers: list[Paper]
):
    """Test finding a paper that doesn't exist."""
    await collection.add_papers(sample_papers)

    # Create a paper with no matching links or title
    search_paper = Paper(
        title="Non-existent Paper",
        links=[Link(type="doi", link="10.1000/nonexistent")],
    )
    found = await collection.find_paper(search_paper)

    assert found is None


async def test_find_paper_prioritizes_links_over_title(
    collection: PaperCollection, sample_paper: Paper
):
    """Test that find_paper prioritizes link matches over title matches."""
    # Add a paper with a specific title
    paper1 = Paper(title=sample_paper.title, links=sample_paper.links)
    await collection.add_papers([paper1])

    # Add another paper with the same title but different links
    paper2 = Paper(title=sample_paper.title)
    await collection.add_papers([paper2])

    # Search with a paper that has a matching link but different title
    search_paper = Paper(title="Different Title", links=sample_paper.links)
    found = await collection.find_paper(search_paper)

    # Should find paper1 by link, not paper2 by title
    assert eq(found, paper1)


async def test_search_by_title(
    collection_r: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test searching by title."""
    collection = collection_r
    await collection.add_papers(sample_papers)

    results = [p async for p in collection.search(title=sample_paper.title)]
    assert any(eq(p, sample_paper) for p in results)


async def test_search_by_author(
    collection_r: PaperCollection, sample_papers: list[Paper]
):
    """Test searching by author."""
    collection = collection_r
    await collection.add_papers(sample_papers)

    results = sorted(
        [p async for p in collection.search(author="Yoshua Bengio")],
        key=lambda x: x.title,
    )
    assert eq(results, sample_papers)

    results = sorted(
        [p async for p in collection.search(author="Hugo Larochelle")],
        key=lambda x: x.title,
    )
    assert len(results) == 3

    results = sorted(
        [p async for p in collection.search(author="Pascal Vincent")],
        key=lambda x: x.title,
    )
    assert len(results) == 1

    results = sorted(
        [p async for p in collection.search(author="Guillaume Alain")],
        key=lambda x: x.title,
    )
    assert len(results) == 1


async def test_search_by_institution(
    collection_r: PaperCollection, sample_papers: list[Paper]
):
    collection = collection_r

    """Test searching by institution."""
    await collection.add_papers(sample_papers)

    results = [p async for p in collection.search(institution="MILA")]
    assert len(results) == 4

    for author_name in AUTHORS_WITH_FAKE_INSTITUTION:
        assert eq(
            [p async for p in collection.search(institution=f"{author_name} Uni")],
            [p async for p in collection.search(author=author_name)],
        )


async def test_search_multiple_criteria(
    collection_r: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test searching with multiple criteria."""
    collection = collection_r

    await collection.add_papers(sample_papers)

    # Search for papers with sample_paper title AND "Guillaume Alain" as author
    results = [
        p
        async for p in collection.search(
            title=sample_paper.title, author="Guillaume Alain"
        )
    ]
    assert not results

    # Search for papers with "Hugo Larochelle Uni" in institution AND "Pascal Vincent" as author
    results = [
        p
        async for p in collection.search(
            institution="Hugo Larochelle Uni", author="Pascal Vincent"
        )
    ]
    assert eq(results, [p async for p in collection.search(author="Pascal Vincent")])


async def test_search_case_insensitive(
    collection_r: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test that search is case insensitive."""
    collection = collection_r

    await collection.add_papers(sample_papers)

    results = [p async for p in collection.search(title=sample_paper.title.upper())]
    assert eq(results, [sample_paper])

    results = [
        p
        async for p in collection.search(
            author=sample_paper.authors[0].display_name.upper()
        )
    ]
    assert results
    assert eq(
        results,
        [p async for p in collection.search(author=sample_paper.authors[0].display_name)],
    )

    results = [
        p async for p in collection.search(institution="Hugo Larochelle Uni".upper())
    ]
    assert eq(
        results, [p async for p in collection.search(institution="Hugo Larochelle Uni")]
    )


async def test_search_no_criteria(
    collection_r: PaperCollection, sample_papers: list[Paper]
):
    """Test searching with no criteria returns all papers."""
    collection = collection_r

    await collection.add_papers(sample_papers)

    results = [p async for p in collection.search()]
    assert eq(results, sample_papers)


async def test_search_partial_matches(
    collection_r: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test that search finds partial matches."""
    collection = collection_r

    await collection.add_papers(sample_papers)

    # Partial title match
    results = [
        p
        async for p in collection.search(
            title=" ".join(sample_paper.title.split(" ")[:3])
        )
    ]
    assert eq(results, [sample_paper])

    # Partial author match
    results = sorted(
        [p async for p in collection.search(author="Yoshua")], key=lambda x: x.title
    )
    assert eq(results, sample_papers)

    # Partial institution match
    results = sorted(
        [p async for p in collection.search(institution="Uni")], key=lambda x: x.title
    )
    assert len(results) == 4


async def test_search_by_flags(collection_r: PaperCollection, sample_papers: list[Paper]):
    """Test searching by flag inclusion and exclusion."""
    collection = collection_r

    await collection.add_papers(sample_papers)

    # Test include_flags: papers must have ALL specified flags
    results = sorted(
        [p async for p in collection.search(include_flags=["valid"])],
        key=lambda x: x.title,
    )
    assert len(results) == 3
    assert all({"valid"} <= p.flags for p in results)

    # Test include_flags with multiple flags: papers must have ALL specified flags
    results = sorted(
        [p async for p in collection.search(include_flags=["valid", "reviewed"])],
        key=lambda x: x.title,
    )
    assert len(results) == 1
    assert all({"valid", "reviewed"} <= p.flags for p in results)

    # Test exclude_flags: papers must NOT have ANY of the specified flags
    results = sorted(
        [p async for p in collection.search(exclude_flags=["invalid"])],
        key=lambda x: x.title,
    )
    assert len(results) == len(sample_papers) - 2
    assert all(not p.flags & {"invalid"} for p in results)

    # Test exclude_flags with multiple flags
    results = sorted(
        [p async for p in collection.search(exclude_flags=["valid", "invalid"])],
        key=lambda x: x.title,
    )
    assert len(results) == len(sample_papers) - 4
    assert all(not p.flags & {"valid", "invalid"} for p in results)

    # Test combining include_flags and exclude_flags
    results = sorted(
        [
            p
            async for p in collection.search(
                include_flags=["valid"], exclude_flags=["invalid"]
            )
        ],
        key=lambda x: x.title,
    )
    assert len(results) == 2
    assert all({"valid"} <= p.flags and not p.flags & {"invalid"} for p in results)

    # Test with no flags (should return all papers)
    results = sorted([p async for p in collection.search()], key=lambda x: x.title)
    assert len(results) == 10


async def test_file_collection_is_persistent(tmp_path: Path, sample_papers: list[Paper]):
    collection = FileCollection(file=tmp_path / "collection.json")

    assert not [p async for p in collection.search()]

    await collection.add_papers(sample_papers)

    assert [p async for p in collection.search()]

    reloaded = FileCollection(file=tmp_path / "collection.json")
    assert [p async for p in collection.search()] == [p async for p in reloaded.search()]
