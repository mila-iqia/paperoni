import inspect
from dataclasses import replace
from typing import Callable

from ovld import ovld

from ..utils import soft_fail


@ovld
async def fetch(typ: str, link: str):
    return None


def register_fetch(f=None, *, tags=None):
    def decorator(f):
        assert inspect.iscoroutinefunction(f), "Registered fetch function must be async"
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


async def _call(f: Callable, *args, force: bool = False, **kwargs) -> tuple:
    f_sig = inspect.signature(f)
    if "force" in f_sig.parameters:
        return await f(*args, force=force, **kwargs)
    else:
        return await f(*args, **kwargs)


# TODO: refactor this to simplify the logic and use pdf refine the same way
# other refines are and not have 2 links management logics in fetch_all
# FOR EACH sws IN work.top:
#     # Compute cheap refine on all links
#     FOR EACH link IN sws.value.links:
#         refine(link)
#
#     # Compute the new score
#     sws.score = work.focuses.score(sws.value)
#
#     # If the new score is not good enough, rerun the refine until we get a pdf
#     # result (or a result associated to the tags we passed as input).
#     IF sws.score < threshold THEN:
#         FOR EACH link IN sws.value.links:
#             IF refine(link, tags=tags)
#                 BREAK
async def fetch_all(links, group="composite", statuses=None, tags=None, force=False):
    statuses = statuses or {}
    tags = tags or {"normal"}

    funcs = [(group, (links,), fetch.resolve_all(links))]
    for type, link in links:
        funcs.append((f"{type}:{link}", (type, link), fetch.resolve_all(type, link)))

    async def go(key, args, f):
        __trace__ = f"refine:{key}"  # noqa: F841
        with soft_fail(f"Refinement of {key}"):
            try:
                paper = await _call(f.func, *args, force=force)
                if paper is not None:
                    statuses[nk] = "found"
                    return replace(
                        paper,
                        key=nk,
                        info={"refined_by": {name: key}},
                    )
                else:
                    statuses[nk] = "not_found"
            except Exception:
                statuses[nk] = "error"
                raise

    for key, args, fs in funcs:
        for f in fs:
            if not _test_tags(getattr(f.func, "tags", {"normal"}), tags):
                continue

            name = getattr(f.func, "description", "???")
            nk = f"{name}/{key}"
            if nk in statuses:
                continue
            statuses[nk] = "pending"
            result = await go(key, args, f)
            if result is not None:
                yield result
