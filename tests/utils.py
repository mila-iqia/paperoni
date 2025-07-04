# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
import dataclasses
import json
from datetime import date, datetime
from typing import Any, Generator

from paperoni.model.classes import Institution, Paper


def iter_affiliations(paper: Paper) -> Generator[Institution, None, None]:
    for author in paper.authors:
        for affiliation in author.affiliations:
            yield affiliation


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
