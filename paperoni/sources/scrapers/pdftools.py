import re
import subprocess
import unicodedata
from bisect import insort

import requests
from tqdm import tqdm

from ...model import Institution, InstitutionCategory
from ...tools import keyword_decorator, similarity

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


def _name_fulltext_affiliations(
    author, method, fulltext, institutions, blockers
):
    for name in sorted(author.aliases, key=len, reverse=True):
        if aff := method(name, fulltext, institutions, blockers):
            return aff
    else:
        return None


def find_fulltext_affiliations(paper, fulltext, institutions):
    blockers = [author.author.name for author in paper.authors]
    findings = [
        (
            (
                aff := {
                    aa.author: _name_fulltext_affiliations(
                        aa.author, method, fulltext, institutions, blockers
                    )
                    or []
                    for aa in paper.authors
                }
            ),
            (len([x for x in aff.values() if x]), -i),
        )
        for i, (_, method) in enumerate(affiliation_extractors)
    ]

    findings.sort(key=lambda row: row[1], reverse=True)
    aff, (score, _) = findings[0]
    if score:
        return aff
    else:
        return None


triggers = {
    "Mila": InstitutionCategory.academia,
    "MILA": InstitutionCategory.academia,
    "Université": InstitutionCategory.academia,
    "Universite": InstitutionCategory.academia,
    "University": InstitutionCategory.academia,
    "Polytechnique": InstitutionCategory.academia,
    "Montréal": InstitutionCategory.academia,
    "Québec": InstitutionCategory.academia,
}

index_re = r"[, †‡\uE005?∗*0-9]+"


def recognize_institution(entry, institutions):
    normalized = unicodedata.normalize("NFKC", entry.strip())
    if entry and normalized in institutions:
        return [institutions[normalized]]
    elif (
        entry
        and any((trigger := t) in entry for t in triggers)
        and "@" not in entry
    ):
        return [Institution(name=entry, aliases=[], category=triggers[trigger])]
    else:
        return []


def should_break(line, blockers):
    """Return True if the line is similar enough to one of the blockers.

    This signifies that the line we are reading pertains to an author of the
    paper and probably starts a new section, so we should ignore it and what
    goes below it.
    """
    return any(similarity(line, blocker) > 0.5 for blocker in blockers)


def _find_fulltext_affiliation_by_footnote(
    name, fulltext, institutions, blockers, splitter
):
    name_re = name.replace(".", "[^ ]*")
    if m := re.search(
        pattern=rf"{name_re}(\n?{index_re})",
        string=fulltext,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        indexes = [
            x for x in splitter(m.groups()[0]) if x not in (" ", ",", "\n")
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
                    if should_break(entry, blockers):
                        break
                    affiliations += recognize_institution(entry, institutions)
        return affiliations


@affiliation_extractor(priority=101)
def find_fulltext_affiliation_by_footnote(
    name, fulltext, institutions, blockers
):
    def splitter(x):
        return re.findall(pattern=r"[0-9]+|.", string=x)

    return _find_fulltext_affiliation_by_footnote(
        name, fulltext, institutions, blockers, splitter=splitter
    )


@affiliation_extractor(priority=100)
def find_fulltext_affiliation_by_footnote_2(
    name, fulltext, institutions, blockers
):
    return _find_fulltext_affiliation_by_footnote(
        name, fulltext, institutions, blockers, splitter=list
    )


@affiliation_extractor(priority=90)
def find_fulltext_affiliation_under_name(
    name, fulltext, institutions, blockers
):
    # Replace . by a regexp, so that B. Smith will match Bernard Smith, Bob Smith, etc.
    name_re = name.replace(".", "[^ ]*")
    if m := re.search(
        pattern=rf"{name_re}(?:\n{index_re})?(?:[ \n*]+)?((?:.*\n){{5}})",
        string=fulltext,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        affiliations = []
        for line in re.split(string=m.groups()[0], pattern=r"[,\n]+"):
            entry = line.strip()
            if should_break(entry, blockers):
                break
            affiliations += recognize_institution(entry, institutions)
        return affiliations
    return None
