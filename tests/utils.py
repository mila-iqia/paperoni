# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
from typing import Generator, Iterable

from paperoni.model import Institution, Paper, PaperInfo, Release, VenueType


def iter_affiliations(paper: Paper) -> Generator[Institution, None, None]:
    for author in paper.authors:
        for affiliation in author.affiliations:
            yield affiliation


def iter_releases(paper: Paper) -> Generator[Release, None, None]:
    for release in paper.releases:
        yield release


def iter_links_ids(paper: Paper) -> Generator[str, None, None]:
    for link in paper.links:
        if link.link:
            yield link.link


def split_on(string: str, separators: Iterable[str] = (" ", "-", "_")) -> list[str]:
    splits = [string]
    for sep in separators:
        splits = sum([part.split(sep) for part in splits], [])
    return [part for part in splits if part.strip()]


def iter_conference_papers(papers: list[PaperInfo]) -> Generator[PaperInfo, None, None]:
    return (
        paper
        for paper in papers
        if any(
            release.venue.type in {VenueType.conference, VenueType.journal}
            for release in iter_releases(paper.paper)
        )
    )


def filter_test_papers(
    papers: list[PaperInfo], titles: Iterable[str]
) -> Generator[PaperInfo, None, None]:
    titles = {title.lower() for title in titles}
    return (
        paper
        for paper in iter_conference_papers(papers)
        if paper.paper.title.lower() in titles
    )
