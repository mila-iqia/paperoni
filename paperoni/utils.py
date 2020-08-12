import unicodedata

import requests
from blessed import Terminal
from hrepr import HTML
from tqdm import tqdm

H = HTML()
T = Terminal()


class PaperoniError(Exception):
    pass


def print_field(title, contents, bold=False):
    """Prints a line that goes 'title: contents', nicely formatted."""
    title = T.bold_cyan(f"{title}:")
    contents = T.bold(contents) if bold else contents
    print(title, contents)


def join(elems, sep=", ", lastsep=None):
    """Create a list using the given separators.

    If lastsep is None, lastsep = sep.

    Returns:
        [elem0, (sep, elem1), (sep, elem2), ... (lastsep, elemn)]
    """
    if lastsep is None:
        lastsep = sep
    elems = list(elems)
    if len(elems) <= 1:
        return elems
    results = [elems[0]]
    for elem in elems[1:-1]:
        results.extend((H.raw(sep), elem))
    results.extend((H.raw(lastsep), elems[-1]))
    return results


def download(url, filename):
    """Download the given url into the given filename."""
    print(f"Downloading {url}")
    r = requests.get(url, stream=True)
    total = int(r.headers.get("content-length") or "1024")
    with open(filename, "wb") as f:
        with tqdm(total=total) as progress:
            for chunk in r.iter_content(chunk_size=total // 100):
                f.write(chunk)
                f.flush()
                progress.update(len(chunk))
    print(f"Saved {filename}")


def asciiify(s):
    """Translate a string to pure ASCII, removing accents and the like.

    Non-ASCII characters that are not accented characters are removed.
    """
    norm = unicodedata.normalize("NFD", s)
    stripped = norm.encode("ASCII", "ignore")
    return stripped.decode("utf8")
