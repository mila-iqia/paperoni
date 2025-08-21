from ovld import ovld

from ..model import PaperInfo


@ovld
def fetch(type: str, link: str):
    return None


def register_fetch(f):
    f.description = f.__name__
    fetch.register(f)
    return f


def fetch_all(type, link, statuses=None):
    statuses = statuses or {}
    for f in fetch.resolve_all(type, link):
        name = getattr(f.func, "description", "???")
        key = f"{type}:{link}"
        nk = name, key
        if nk in statuses:
            continue
        statuses[nk] = "pending"
        try:
            paper = f()
            if paper is not None:
                statuses[nk] = "found"
                yield PaperInfo(paper=paper, key=key, info={"refined_by": {name: key}})
            else:
                statuses[nk] = "not_found"
        except Exception:
            statuses[nk] = "error"
            raise
