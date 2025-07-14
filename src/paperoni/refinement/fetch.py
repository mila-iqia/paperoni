from ovld import ovld

from ..model import PaperInfo


@ovld
def fetch(type: str, link: str):
    return None


def fetch_all(type, link):
    for f in fetch.resolve_all(type, link):
        paper = f()
        if paper is not None:
            yield PaperInfo(paper=paper, key=f"{type}:{link}")
