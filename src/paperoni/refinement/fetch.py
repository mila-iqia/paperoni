import inspect
from typing import Callable

from ovld import ovld

from ..model import PaperInfo
from ..utils import soft_fail


@ovld
def fetch(type: str, link: str):
    return None


def register_fetch(f=None, *, tags=None):
    def decorator(f):
        f.description = f.__name__
        f.tags = tags or {"normal"}
        f.tags.add(f.__name__)
        fetch.register(f)
        return f

    if f is None:
        return decorator
    else:
        return decorator(f)


def _test_tags(f_tags: set, tags: set) -> bool:
    return "all" in tags or not (tags - f_tags)


def _call(f: Callable, *args, force: bool = False, **kwargs) -> tuple:
    f_sig = inspect.signature(f)
    if "force" in f_sig.parameters:
        return f(*args, force=force, **kwargs)
    else:
        return f(*args, **kwargs)


def fetch_all(links, group="composite", statuses=None, tags=None, force=False):
    statuses = statuses or {}
    tags = tags or {"normal"}

    funcs = [(group, (links,), fetch.resolve_all(links))]
    for type, link in links:
        funcs.append((f"{type}:{link}", (type, link), fetch.resolve_all(type, link)))

    for key, args, fs in funcs:
        for f in fs:
            with soft_fail(f"Refinement of {key}"):
                if not _test_tags(getattr(f.func, "tags", {"normal"}), tags):
                    continue

                name = getattr(f.func, "description", "???")
                nk = name, key
                if nk in statuses:
                    continue
                statuses[nk] = "pending"
                try:
                    paper = _call(f.func, *args, force=force)
                    if paper is not None:
                        statuses[nk] = "found"
                        yield PaperInfo(
                            paper=paper,
                            key=key,
                            info={"refined_by": {name: key}},
                        )
                    else:
                        statuses[nk] = "not_found"
                except Exception:
                    statuses[nk] = "error"
                    raise
