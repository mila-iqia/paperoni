from ovld import ovld

from ..model import PaperInfo


@ovld
def fetch(type: str, link: str):
    return None


def register_fetch(f):
    f.description = f.__name__
    fetch.register(f)
    return f


def fetch_all(type, link):
    for f in fetch.resolve_all(type, link):
        paper = f()
        name = getattr(f.func, "description", "???")
        key = f"{type}:{link}"
        if paper is not None:
            yield PaperInfo(paper=paper, key=key, info={"refined_by": {name: key}})
