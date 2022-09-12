import re
import subprocess
import unicodedata
from bisect import insort

import requests
from tqdm import tqdm

from ...tools import keyword_decorator

affiliation_extractors = []


@keyword_decorator
def affiliation_extractor(fn, *, priority):
    insort(affiliation_extractors, (-priority, fn))
    return fn


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


def pdf_to_text(cache_base, url):
    cache_base.parent.mkdir(exist_ok=True)

    pdf = cache_base.with_suffix(".pdf")
    if not pdf.exists():
        download(filename=pdf, url=url)

    html = pdf.with_suffix(".html")
    if not html.exists():
        subprocess.run(["pdf2htmlEX", str(pdf), str(html)])

    txt = pdf.with_suffix(".txt")
    if not txt.exists():
        subprocess.run(
            ["html2text", "-width", "1000", "-o", str(txt), str(html)]
        )

    fulltext = open(txt).read()
    fulltext = re.sub(string=fulltext, pattern="-\n(?![0-9])", repl="")
    fulltext = re.sub(string=fulltext, pattern=",\n(?![0-9])", repl=", ")
    fulltext = re.sub(
        string=fulltext, pattern="\n´\n([a-zA-Z])", repl="\\1\u0301"
    )
    fulltext = re.sub(
        string=fulltext, pattern="\n\u02DC\n([a-zA-Z])", repl="\\1\u0303"
    )

    fulltext = unicodedata.normalize("NFKC", fulltext.strip())

    return fulltext


def _name_fulltext_affiliations(author, method, fulltext, institutions):
    for name in sorted(author.aliases, key=len, reverse=True):
        if aff := method(name, fulltext, institutions):
            return aff
    else:
        return None


def find_fulltext_affiliations(paper, fulltext, institutions):
    for _, method in affiliation_extractors:
        aff = {
            aa.author: _name_fulltext_affiliations(
                aa.author, method, fulltext, institutions
            )
            or []
            for aa in paper.authors
        }
        if any(x for x in aff.values()):
            return aff
    else:
        return None


@affiliation_extractor(priority=100)
def find_fulltext_affiliation_by_footnote(name, fulltext, institutions):
    if m := re.search(
        pattern=rf"{name}(\n?[, †‡\uE005?∗*0-9]+)",
        string=fulltext,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        indexes = [
            x
            for x in re.findall(pattern=r"[0-9]+|.", string=m.groups()[0])
            if x not in (" ", ",", "\n")
        ]
        affiliations = []

        for idx in indexes:
            idx = idx.replace("*", r"\*")
            idx = idx.replace("?", r"\?")
            for result in re.findall(
                pattern=rf"\n{idx}(?=\n(.*)\n)|\n{idx}:(?=(.*)\n)",
                string=fulltext,
            ):
                result = result[0] or result[1]
                for entry in result.split(","):
                    entry = unicodedata.normalize("NFKC", entry.strip())
                    if entry and entry in institutions:
                        affiliations.append(institutions[entry])
        return affiliations


@affiliation_extractor(priority=90)
def find_fulltext_affiliation_under_name(name, fulltext, institutions):
    if m := re.search(
        pattern=rf"{name}(?:[ \n*]+)?((?:.*\n){{2}})",
        string=fulltext,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        affiliations = []
        for line in re.split(string=m.groups()[0], pattern=r"[,\n]+"):
            entry = line.strip()
            if entry and entry in institutions:
                affiliations.append(institutions[entry])
        return affiliations
    return None
