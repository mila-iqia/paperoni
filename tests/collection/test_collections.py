import copy
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import Generator

import gifnoc
import pytest
from easy_oauth.testing.utils import AppTester
from ovld import ovld
from pytest_regressions.data_regression import DataRegressionFixture
from serieux import serialize

from paperoni.collection.abc import PaperCollection, _id_types
from paperoni.collection.filecoll import FileCollection
from paperoni.collection.memcoll import MemCollection
from paperoni.collection.mongocoll import MongoCollection, MongoPaper
from paperoni.collection.remotecoll import RemoteCollection
from paperoni.discovery.jmlr import JMLR
from paperoni.model.classes import (
    CollectionPaper,
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
        return a == b


@ovld
def eq(a: dict, b: dict):
    for k in set(a) & set(b):
        if not eq(a[k], b[k]):
            return False
    return True


@pytest.fixture(scope="session")
def sample_papers() -> Generator[list[Paper], None, None]:
    discoverer = JMLR()

    volumes: list[str] = []
    for volume in sorted(discoverer.list_volumes(), key=lambda x: int(x.lstrip("v"))):
        if volume == "v25":
            break
        volumes.append(volume)

    papers: list[PaperInfo] = []
    for volume in volumes:
        papers.extend(discoverer.query(volume=volume, name="Yoshua Bengio"))

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
    memcol.add_papers(sample_papers)
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


@pytest.fixture(params=[MemCollection, FileCollection, MongoCollection, RemoteCollection])
def collection(
    request, tmp_path: Path, app_coll
) -> Generator[PaperCollection, None, None]:
    if request.param == MemCollection:
        yield MemCollection()

    elif request.param == FileCollection:
        yield FileCollection(file=tmp_path / "collection.json")

    elif request.param == MongoCollection:
        safe_to_drop = False
        try:
            mongo_collection = MongoCollection(database=tmp_path.name)
            assert (
                not list(mongo_collection.search()) and not mongo_collection.exclusions
            ), dedent(
                """Mongo collection is not empty. As tests will purge the database,
                empty the database before running the tests to avoid unwanted loss
                of data."""
            )
            safe_to_drop = True
            yield mongo_collection

        finally:
            if safe_to_drop:
                mongo_collection._client.drop_database(mongo_collection.database)

    elif request.param == RemoteCollection:
        if request.node.get_closest_marker("coll_w_remote"):
            coll = RemoteCollection(endpoint="http://localhost:18888/api/v1")

            class Proxy:
                def __getattr__(self, name):
                    attr = getattr(coll, name)
                    if name in ["search"]:
                        return attr

                    if callable(attr):
                        return lambda *args, **kwargs: None
                    else:
                        return None

            yield Proxy()

        else:
            pytest.skip(
                "RemoteCollection does not implement all collection methods needed for this test"
            )


def test_add_papers(collection: PaperCollection, sample_papers: list[Paper]):
    """Test adding multiple papers."""
    collection.add_papers(sample_papers)

    assert eq(list(collection.search()), sample_papers)


def test_drop_collection(collection: PaperCollection, sample_papers: list[Paper]):
    """Test dropping a collection."""
    collection.add_papers(sample_papers)

    collection.drop()

    assert not list(collection.search())


def test_exclude_papers_multiple(
    collection: PaperCollection,
    sample_papers: list[Paper],
    excluded_papers: list[Paper],
):
    """Test excluding multiple papers."""
    collection.exclude_papers(excluded_papers)

    collection.add_papers(sample_papers)

    for excluded_paper in excluded_papers:
        assert not list(collection.search(title=excluded_paper.title))


def test_exclude_papers_unknown_link_type(collection: PaperCollection):
    """Test excluding papers with unknown link types."""
    paper = Paper(
        title="Unknown Links",
        links=[
            Link(type="unknown", link="some-link"),
        ],
    )
    collection.exclude_papers([paper])

    collection.add_papers([paper])

    assert eq(list(collection.search()), [paper])


def test_find_paper_by_link(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test finding a paper by its link."""
    collection.add_papers(sample_papers)

    # Create a paper with a matching link
    search_paper = Paper(title="Search Paper by Link", links=sample_paper.links[0:1])
    found = collection.find_paper(search_paper)

    assert eq(found, sample_paper)


def test_find_paper_by_title(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test finding a paper by its title."""
    collection.add_papers(sample_papers)

    # Create a paper with a matching title but no matching links
    search_paper = Paper(title=sample_paper.title, authors=sample_paper.authors)
    found = collection.find_paper(search_paper)

    assert eq(found, sample_paper)


def test_find_paper_not_found(collection: PaperCollection, sample_papers: list[Paper]):
    """Test finding a paper that doesn't exist."""
    collection.add_papers(sample_papers)

    # Create a paper with no matching links or title
    search_paper = Paper(
        title="Non-existent Paper",
        links=[Link(type="doi", link="10.1000/nonexistent")],
    )
    found = collection.find_paper(search_paper)

    assert found is None


def test_find_paper_prioritizes_links_over_title(
    collection: PaperCollection, sample_paper: Paper
):
    """Test that find_paper prioritizes link matches over title matches."""
    # Add a paper with a specific title
    paper1 = Paper(title=sample_paper.title, links=sample_paper.links)
    collection.add_papers([paper1])

    # Add another paper with the same title but different links
    paper2 = Paper(title=sample_paper.title)
    collection.add_papers([paper2])

    # Search with a paper that has a matching link but different title
    search_paper = Paper(title="Different Title", links=sample_paper.links)
    found = collection.find_paper(search_paper)

    # Should find paper1 by link, not paper2 by title
    assert eq(found, paper1)


@pytest.mark.coll_w_remote
def test_search_by_title(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test searching by title."""
    collection.add_papers(sample_papers)

    results = list(collection.search(title=sample_paper.title))
    assert any(eq(p, sample_paper) for p in results)


@pytest.mark.coll_w_remote
def test_search_by_author(collection: PaperCollection, sample_papers: list[Paper]):
    """Test searching by author."""
    collection.add_papers(sample_papers)

    results = sorted(collection.search(author="Yoshua Bengio"), key=lambda x: x.title)
    assert eq(results, sample_papers)

    results = sorted(collection.search(author="Hugo Larochelle"), key=lambda x: x.title)
    assert len(results) == 3

    results = sorted(collection.search(author="Pascal Vincent"), key=lambda x: x.title)
    assert len(results) == 1

    results = sorted(collection.search(author="Guillaume Alain"), key=lambda x: x.title)
    assert len(results) == 1


@pytest.mark.coll_w_remote
def test_search_by_institution(collection: PaperCollection, sample_papers: list[Paper]):
    """Test searching by institution."""
    collection.add_papers(sample_papers)

    results = list(collection.search(institution="MILA"))
    assert len(results) == 4

    for author_name in AUTHORS_WITH_FAKE_INSTITUTION:
        assert eq(
            list(collection.search(institution=f"{author_name} Uni")),
            list(collection.search(author=author_name)),
        )


@pytest.mark.coll_w_remote
def test_search_multiple_criteria(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test searching with multiple criteria."""
    collection.add_papers(sample_papers)

    # Search for papers with sample_paper title AND "Guillaume Alain" as author
    results = list(collection.search(title=sample_paper.title, author="Guillaume Alain"))
    assert not results

    # Search for papers with "Hugo Larochelle Uni" in institution AND "Pascal Vincent" as author
    results = list(
        collection.search(institution="Hugo Larochelle Uni", author="Pascal Vincent")
    )
    assert eq(results, list(collection.search(author="Pascal Vincent")))


@pytest.mark.coll_w_remote
def test_search_case_insensitive(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test that search is case insensitive."""
    collection.add_papers(sample_papers)

    results = list(collection.search(title=sample_paper.title.upper()))
    assert eq(results, [sample_paper])

    results = list(collection.search(author=sample_paper.authors[0].display_name.upper()))
    assert results
    assert eq(
        results, list(collection.search(author=sample_paper.authors[0].display_name))
    )

    results = list(collection.search(institution="Hugo Larochelle Uni".upper()))
    assert eq(results, list(collection.search(institution="Hugo Larochelle Uni")))


@pytest.mark.coll_w_remote
def test_search_no_criteria(collection: PaperCollection, sample_papers: list[Paper]):
    """Test searching with no criteria returns all papers."""
    collection.add_papers(sample_papers)

    results = list(collection.search())
    assert eq(results, sample_papers)


@pytest.mark.coll_w_remote
def test_search_partial_matches(
    collection: PaperCollection, sample_papers: list[Paper], sample_paper: Paper
):
    """Test that search finds partial matches."""
    collection.add_papers(sample_papers)

    # Partial title match
    results = list(collection.search(title=" ".join(sample_paper.title.split(" ")[:3])))
    assert eq(results, [sample_paper])

    # Partial author match
    results = sorted(collection.search(author="Yoshua"), key=lambda x: x.title)
    assert eq(results, sample_papers)

    # Partial institution match
    results = sorted(collection.search(institution="Uni"), key=lambda x: x.title)
    assert len(results) == 4


def test_file_collection_is_persistent(tmp_path: Path, sample_papers: list[Paper]):
    collection = FileCollection(file=tmp_path / "collection.json")

    assert not list(collection.search())

    collection.add_papers(sample_papers)

    assert list(collection.search())

    assert list(collection.search()) == list(
        # Reload the collection from the file
        FileCollection(file=tmp_path / "collection.json").search()
    )


@pytest.mark.parametrize("paper_cls", [CollectionPaper, MongoPaper])
def test_make_collection_item(
    data_regression: DataRegressionFixture,
    collection: PaperCollection,
    sample_papers: list[Paper],
    paper_cls: type[CollectionPaper],
):
    """Test making a collection."""
    collection.add_papers(sample_papers)

    papers = list(collection.search())
    assert eq(papers, sample_papers)

    paper = paper_cls.make_collection_item(papers[0])

    if paper_cls is type(papers[0]):
        assert paper == papers[0]
    else:
        assert paper.id == papers[0].id
        assert eq(paper, papers[0])

    paper = serialize(paper_cls, paper)
    # MongoPaper uses ObjectId which will not be the same each time the test is
    # run
    paper["id"] = None if not isinstance(paper["id"], int) else paper["id"]
    paper.pop("_id", None)
    paper.pop("version")
    data_regression.check(paper)
