# json.dumps does not sort embedded lists, this custom function should allow to
# reproduce the same output
import json
from typing import Any


def sort_keys(obj: dict | list | Any) -> dict | list:
    if isinstance(obj, dict):
        return {k: sort_keys(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        _list = list(map(sort_keys, obj))
        return sorted(_list, key=lambda x: json.dumps(x, sort_keys=True))
    else:
        return obj
