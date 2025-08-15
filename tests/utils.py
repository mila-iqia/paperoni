# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
from typing import Generator, Iterable

from pytest_regressions.data_regression import DataRegressionFixture
from serieux import deserialize, serialize

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


def check_papers(data_regression: DataRegressionFixture, papers: list[PaperInfo]):
    # Using file_regression and json.dumps to avoid
    # yaml.representer.RepresenterError on DatePrecision
    # papers = sort_keys(papers[:5])
    # [p.pop("acquired") for p in papers]
    papers = serialize(list[PaperInfo], papers[:5])

    # make sure we can deserialize the papers
    deserialize(list[PaperInfo], papers)

    [p.pop("acquired") for p in papers]
    data_regression.check(papers)


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
