from ovld import ovld

from ...model import PaperInfo


@ovld
def fetch_pdf(type: str, link: str):
    return None, None


def register_fetch(f):
    f.description = f.__name__
    fetch_pdf.register(f)
    return f


def fetch_all(type, link, force: bool = False):
    for f in fetch_pdf.resolve_all(type, link, force):
        name = getattr(f.func, "description", "???")
        paper, subkey = f()
        key = f"{type}:{link}"
        if paper is not None:
            yield PaperInfo(
                paper=paper, key=key, info={"refined_by": {f"{name}:{subkey}": key}}
            )
