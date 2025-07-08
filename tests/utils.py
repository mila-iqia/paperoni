# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
import dataclasses
import json
from datetime import date, datetime
from typing import Any, Generator, Iterable

from pytest_regressions.file_regression import FileRegressionFixture

from paperoni.discovery.base import PaperInfo
from paperoni.model.classes import Institution, Paper, Release


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


# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output.
# serialize(list[Paper], ...) also seams to fail with
# yaml.emitter.EmitterError: expected NodeEvent, but got DocumentEndEvent()
def sort_keys(obj: dict | list | Any) -> dict | list:
    if dataclasses.is_dataclass(obj):
        obj = vars(obj)

    if isinstance(obj, dict):
        return {k: sort_keys(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        _list = list(map(sort_keys, obj))
        return sorted(_list, key=lambda x: json.dumps(x, sort_keys=True))
    elif isinstance(obj, datetime) or isinstance(obj, date):
        return obj.isoformat()
    else:
        return obj


def check_papers(file_regression: FileRegressionFixture, papers: list[PaperInfo]):
    # Using file_regression and json.dumps to avoid
    # yaml.representer.RepresenterError on DatePrecision
    papers = sort_keys(papers[:5])
    [p.pop("acquired") for p in papers]
    file_regression.check(
        json.dumps(sort_keys(papers[:5]), indent=2, ensure_ascii=False),
        extension=".json",
    )
