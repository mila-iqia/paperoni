import re
import shutil
import textwrap
import unicodedata
from collections import defaultdict

import requests
from blessed import Terminal
from hrepr import H
from tqdm import tqdm

T = Terminal()
tw = shutil.get_terminal_size((80, 20)).columns


class PaperoniError(Exception):
    pass


def print_field(title, contents, bold=False):
    """Prints a line that goes 'title: contents', nicely formatted."""
    contents = textwrap.fill(f"{title}: {contents}", width=tw)[len(title) + 2 :]
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


def get_content_type(url):
    """Return the 'content-type' header from given URL."""
    r = requests.head(url)
    return r.headers.get("content-type", None)


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


def group_by(papers, key):
    """Group a sequence by the result of a key function."""
    groups = defaultdict(list)
    for p in papers:
        groups[key(p)].append(p)
    return groups


def normalize(s):
    if s is None:
        return None
    else:
        return asciiify(s).lower()


REGEX_URL = re.compile(r"^[a-z]+://")
REGEX_WORD_THEN_NUMBER = re.compile(r"([^0-9 ])([0-9])")
REGEX_NUMBER_THEN_WORD = re.compile(r"([0-9])([^0-9 ])")
REGEX_NO_WORD = re.compile(r"((\W|_)+)")
REGEX_SEQ_NO_WORD = re.compile(r"( (\W|_)){2,}")
REGEX_NUMBER = re.compile(r"^[0-9]+$")
REGEX_VOLUME = re.compile(r"^volume$", re.IGNORECASE)
REGEX_VOL = re.compile(r"^vol$", re.IGNORECASE)
WRITTEN_NUMBERS = {
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
    "twentieth",
}
RANK_SUFFIXES = {"st", "nd", "rd", "th"}


def _list_starts_with(inp: list, search: list, start=0):
    if len(inp) - start < len(search):
        return None
    for j in range(len(search)):
        piece = inp[start + j]
        pattern = search[j]
        if not (
            (isinstance(pattern, str) and pattern == piece)
            or (isinstance(pattern, re.Pattern) and pattern.match(piece))
        ):
            return None
    else:
        # No break encountered, ie. full pattern found.
        return inp[start : (start + len(search))]


def get_venue_name_and_volume(venue: str):
    """Try to infer venue name and volume from given venue long name.

    Return a couple (inferred venue name, inferred venue volume)
    Inferred venue volume is None if no volume was detected.
    """
    venue = venue.strip()
    # We don't try to parse URLs.
    if REGEX_URL.match(venue):
        return venue, None
    # Separate word then number with a space.
    venue = REGEX_WORD_THEN_NUMBER.sub(r"\1 \2", venue)
    # Separate number then word with a space.
    venue = REGEX_NUMBER_THEN_WORD.sub(r"\1 \2", venue)
    # Make sure to put spaces around any punctuation sequence.
    venue = REGEX_NO_WORD.sub(r" \1 ", venue)
    # Split venue on spaces.
    pieces = venue.split()
    inferred_volume = []
    inferred_name = []
    cursor = 0
    while cursor < len(pieces):
        piece = pieces[cursor]
        if not piece:
            continue
        explicit_volume = _list_starts_with(
            pieces, [REGEX_VOLUME, REGEX_NUMBER], cursor
        ) or _list_starts_with(pieces, [REGEX_VOL, ".", REGEX_NUMBER], cursor)
        if explicit_volume:
            inferred_volume.append(f"volume {explicit_volume[-1]}")
            cursor += len(explicit_volume)
        elif piece.lower() in WRITTEN_NUMBERS:
            inferred_volume.append(piece)
            cursor += 1
        elif REGEX_NUMBER.match(piece):
            volume = piece
            cursor += 1
            if cursor < len(pieces) and pieces[cursor].lower() in RANK_SUFFIXES:
                volume += pieces[cursor]
                cursor += 1
            inferred_volume.append(volume)
        else:
            inferred_name.append(piece)
            cursor += 1
    # Replace consecutive punctuation with last one.
    name = REGEX_SEQ_NO_WORD.sub(
        lambda m: m.group(0)[-1], " ".join(inferred_name)
    )
    volume = ", ".join(inferred_volume) or None
    # Return inferred name and volume.
    return name, volume
