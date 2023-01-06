import re
import subprocess
import unicodedata
from bisect import insort
from pathlib import Path
from types import SimpleNamespace

import requests
from eventlet.timeout import Timeout
from tqdm import tqdm

from ...config import config
from ...model import Institution, InstitutionCategory
from ...tools import keyword_decorator, similarity
from ..acquire import readpage

affiliation_extractors = []


@keyword_decorator
def affiliation_extractor(fn, *, priority):
    insort(affiliation_extractors, (-priority, fn))
    return fn


def download(url, filename):
    """Download the given url into the given filename."""
    from ...config import config

    def iter_with_timeout(r, chunk_size, timeout):
        it = r.iter_content(chunk_size=chunk_size)
        try:
            while True:
                with Timeout(timeout):
                    yield next(it)
        except StopIteration:
            pass
        finally:
            it.close()

    print(f"Downloading {url}")
    config.get().uninstall()
    try:
        r = requests.get(url, stream=True)
        total = int(r.headers.get("content-length") or "1024")
        with open(filename, "wb") as f:
            with tqdm(total=total) as progress:
                for chunk in iter_with_timeout(
                    r, chunk_size=max(total // 100, 1), timeout=5
                ):
                    f.write(chunk)
                    f.flush()
                    progress.update(len(chunk))
    finally:
        config.get().install()
    print(f"Saved {filename}")


def link_to_pdf_text(link, only_use_cache=False):
    lnk = link.link.replace("/", "__")
    if not lnk.endswith(".pdf"):
        lnk = f"{lnk}.pdf"
    pth = Path(config.get().paths.cache) / link.type / lnk

    if only_use_cache:
        return pdf_to_text(
            cache_base=pth, url=None, only_use_cache=only_use_cache
        )

    match link.type:
        case "arxiv":
            url = f"https://arxiv.org/pdf/{link.link}.pdf"
        case "openreview":
            url = f"https://openreview.net/pdf?id={link.link}"
        case "doi":
            data = readpage(
                f"https://api.crossref.org/v1/works/{link.link}", format="json"
            )
            if (
                data is None
                or data["status"] != "ok"
                or "link" not in data["message"]
            ):
                return None
            data = SimpleNamespace(**data["message"])
            for lnk in data.link:
                if lnk["content-type"] == "application/pdf":
                    url = lnk["URL"]
                    break
            else:
                return None
        case "pdf":
            url = link.link
        case _:
            return None

    return pdf_to_text(cache_base=pth, url=url)


def pdf_to_text(cache_base, url, only_use_cache=False):
    if len(str(cache_base)) > 255:
        return ""

    cache_base.parent.mkdir(parents=True, exist_ok=True)

    pdf = cache_base.with_suffix(".pdf")
    html = pdf.with_suffix(".html")
    txt = pdf.with_suffix(".txt")

    if only_use_cache:
        if txt.exists():
            return txt.read_text()
        else:
            return ""

    if not pdf.exists():
        try:
            download(filename=pdf, url=url)
        except requests.exceptions.SSLError:
            pdf.write_text("")
            html.write_text("")
            txt.write_text(bah := "failure")
            return bah

    if not html.exists():
        _pdf = str(pdf.relative_to(Path.cwd()))
        _html = str(html.relative_to(Path.cwd()))
        subprocess.run(["pdf2htmlEX", _pdf, _html])
        if not html.exists():
            html.write_text("")
            txt.write_text(bah := "failure")
            return bah

    if not txt.exists() or not txt.stat().st_size:
        subprocess.run(
            ["html2text", "-width", "1000", "-o", str(txt), str(html)]
        )

    fulltext = open(txt).read()
    fulltext = re.sub(string=fulltext, pattern="-\n(?![0-9])", repl="")
    fulltext = re.sub(string=fulltext, pattern=",\n(?![0-9])", repl=", ")
    fulltext = re.sub(
        string=fulltext, pattern="\n?´\n?([a-zA-Z])", repl="\\1\u0301"
    )
    fulltext = re.sub(
        string=fulltext, pattern="\n?`\n?([a-zA-Z])", repl="\\1\u0300"
    )
    fulltext = re.sub(
        string=fulltext, pattern="\n?\u02DC\n?([a-zA-Z])", repl="\\1\u0303"
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
    assert fulltext is not None
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


def make_name_re(name):
    return name.replace(" ", "[ \n]+").replace(".", "[^ ]*") + ",?"


def _find_fulltext_affiliation_by_footnote(
    name, fulltext, institutions, blockers, splitter
):
    name_re = make_name_re(name)
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
    name_re = make_name_re(name)
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
