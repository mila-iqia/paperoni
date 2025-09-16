from typing import Any, Generator

import pytest
from ovld import ovld

from paperoni.collection.memcoll import MemCollection, _id_types
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
def eq(a: list[Any], b: list[Any]):
    assert len(a) == len(b)
    return all(eq(a, b) for a, b in zip(a, b))


@ovld
def eq(a: Any, b: Any):
    fields_a = vars(a)
    fields_b = vars(b)
    fields_a = {k: fields_a[k] for k in set(fields_a) & set(fields_b)}
    fields_b = {k: fields_b[k] for k in set(fields_a) & set(fields_b)}
    return fields_a == fields_b


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
    papers = sample_papers[-2:]
    for p in papers:
        for lnk_type in _id_types:
            p.links.append(Link(type=lnk_type, link=f"test_{lnk_type}_{p.title}"))

    yield papers


def test_add_papers_multiple(sample_papers: list[Paper]):
    """Test adding multiple papers."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    assert eq(list(collection.search()), sample_papers)


def test_exclude_papers_multiple(
    sample_papers: list[Paper], excluded_papers: list[Paper]
):
    """Test excluding multiple papers."""
    collection = MemCollection()
    collection.exclude_papers(excluded_papers)

    collection.add_papers(sample_papers)

    for excluded_paper in excluded_papers:
        assert not list(collection.search(title=excluded_paper.title))


def test_exclude_papers_unknown_link_type():
    """Test excluding papers with unknown link types."""
    collection = MemCollection()
    paper = Paper(
        title="Unknown Links",
        links=[
            Link(type="unknown", link="some-link"),
        ],
    )
    collection.exclude_papers([paper])

    collection.add_papers([paper])

    assert eq(list(collection.search()), [paper])


def test_find_paper_by_link(sample_papers: list[Paper], sample_paper: Paper):
    """Test finding a paper by its link."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    # Create a paper with a matching link
    search_paper = Paper(title="Search Paper by Link", links=sample_paper.links[0:1])
    found = collection.find_paper(search_paper)

    assert eq(found, sample_paper)


def test_find_paper_by_title(sample_papers: list[Paper], sample_paper: Paper):
    """Test finding a paper by its title."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    # Create a paper with a matching title but no matching links
    search_paper = Paper(title=sample_paper.title)
    found = collection.find_paper(search_paper)

    assert eq(found, sample_paper)


def test_find_paper_not_found(sample_papers: list[Paper]):
    """Test finding a paper that doesn't exist."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    # Create a paper with no matching links or title
    search_paper = Paper(
        title="Non-existent Paper",
        links=[Link(type="doi", link="10.1000/nonexistent")],
    )
    found = collection.find_paper(search_paper)

    assert found is None


def test_find_paper_prioritizes_links_over_title(sample_paper: Paper):
    """Test that find_paper prioritizes link matches over title matches."""
    collection = MemCollection()

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


def test_search_by_title(sample_papers: list[Paper], sample_paper: Paper):
    """Test searching by title."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    results = list(collection.search(title=sample_paper.title))
    assert any(eq(p, sample_paper) for p in results)


def test_search_by_author(sample_papers: list[Paper]):
    """Test searching by author."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    results = list(collection.search(author="Yoshua Bengio"))
    assert eq(results, sample_papers)

    results = list(collection.search(author="Hugo Larochelle"))
    assert len(results) == 3

    results = list(collection.search(author="Pascal Vincent"))
    assert len(results) == 1

    results = list(collection.search(author="Guillaume Alain"))
    assert len(results) == 1


def test_search_by_institution(sample_papers):
    """Test searching by institution."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    results = list(collection.search(institution="MILA"))
    assert len(results) == 4

    for author_name in AUTHORS_WITH_FAKE_INSTITUTION:
        assert eq(
            list(collection.search(institution=f"{author_name} Uni")),
            list(collection.search(author=author_name)),
        )


def test_search_multiple_criteria(sample_papers: list[Paper], sample_paper: Paper):
    """Test searching with multiple criteria."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    # Search for papers with sample_paper title AND "Guillaume Alain" as author
    results = list(collection.search(title=sample_paper.title, author="Guillaume Alain"))
    assert not results

    # Search for papers with "Hugo Larochelle Uni" in institution AND "Pascal Vincent" as author
    results = list(
        collection.search(institution="Hugo Larochelle Uni", author="Pascal Vincent")
    )
    assert eq(results, list(collection.search(author="Pascal Vincent")))


def test_search_case_insensitive(sample_papers: list[Paper], sample_paper: Paper):
    """Test that search is case insensitive."""
    collection = MemCollection()
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


def test_search_no_criteria(sample_papers):
    """Test searching with no criteria returns all papers."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    results = list(collection.search())
    assert eq(results, sample_papers)


def test_search_partial_matches(sample_papers: list[Paper], sample_paper: Paper):
    """Test that search finds partial matches."""
    collection = MemCollection()
    collection.add_papers(sample_papers)

    # Partial title match
    results = list(collection.search(title=" ".join(sample_paper.title.split(" ")[:3])))
    assert eq(results, [sample_paper])

    # Partial author match
    results = list(collection.search(author="Yoshua"))
    assert eq(results, sample_papers)

    # Partial institution match
    results = list(collection.search(institution="Uni"))
    assert len(results) == 4
