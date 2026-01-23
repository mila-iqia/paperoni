# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
from typing import Generator, Iterable

from ovld import ovld

from paperoni.model import Institution, Paper, Release, VenueType


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


def iter_conference_papers(papers: list[Paper]) -> Generator[Paper, None, None]:
    return (
        paper
        for paper in papers
        if any(
            release.venue.type in {VenueType.conference, VenueType.journal}
            for release in iter_releases(paper)
        )
    )


def filter_test_papers(
    papers: list[Paper], titles: Iterable[str]
) -> Generator[Paper, None, None]:
    titles = {title.lower() for title in titles}
    return (
        paper for paper in iter_conference_papers(papers) if paper.title.lower() in titles
    )


def sort_title(papers):
    return sorted(papers, key=lambda p: p.title)


@ovld
def eq(a: list, b: list):
    return len(a) == len(b) and all(eq(a, b) for a, b in zip(a, b))


@ovld
def eq(a: object, b: object):
    omit = ["version"]
    try:
        fields_a = {
            k: v for k, v in vars(a).items() if not k.startswith("_") and k not in omit
        }
        fields_b = {
            k: v for k, v in vars(b).items() if not k.startswith("_") and k not in omit
        }
        return eq(fields_a, fields_b)
    except TypeError:
        return (a is None) or (b is None) or a == b


@ovld
def eq(a: dict, b: dict):
    for k in set(a) & set(b):
        if not eq(a[k], b[k]):
            return False
    return True
