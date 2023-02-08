import subprocess
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import requests
from eventlet.timeout import Timeout
from tqdm import tqdm

from ...config import config
from ...model import Institution, InstitutionCategory
from ..acquire import readpage
from .pdfanal import (
    classify_superscripts,
    make_document_from_layout,
    normalize,
    undertext,
)


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
    data = pdf.with_suffix(".data")

    if only_use_cache:
        if data.exists():
            return data.read_text()
        else:
            return ""

    if not pdf.exists():
        try:
            download(filename=pdf, url=url)
        except requests.exceptions.SSLError:
            pdf.write_text("")
            data.write_text(bah := "failure")
            return bah

    if True or not data.exists() or not data.stat().st_size:
        subprocess.run(["pdftotext", "-bbox-layout", str(pdf), str(data)])

    fulltext = open(data).read()
    return fulltext


triggers = {
    "Mila": InstitutionCategory.academia,
    "MILA": InstitutionCategory.academia,
    "Université": InstitutionCategory.academia,
    "Universite": InstitutionCategory.academia,
    "University": InstitutionCategory.academia,
    "Polytechnique": InstitutionCategory.academia,
    "Montréal": InstitutionCategory.academia,
    "Québec": InstitutionCategory.academia,
    "Montreal": InstitutionCategory.academia,
    "Quebec": InstitutionCategory.academia,
}


def recognize_institution(entry, institutions):
    normalized = unicodedata.normalize("NFKC", entry.strip().strip(","))
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


def recognize_institutions(lines, institutions):
    affiliations = []
    for line in lines:
        if line.startswith(","):
            continue
        candidates = [line, *line.split(",")]
        for candidate in candidates:
            if insts := recognize_institution(candidate, institutions):
                affiliations += insts
                break
    return affiliations


def find_fulltext_affiliation_by_footnote(doc, superscripts):
    def find(name, institutions):
        nname = normalize(name)
        if nname in superscripts:
            return recognize_institutions(
                set(superscripts[nname]), institutions
            )

    return find


def find_fulltext_affiliation_under_name(doc, extra_margin):
    def find(name, institutions):
        return recognize_institutions(
            (
                line
                for utgrp in undertext(doc, name, extra_margin)
                for line in utgrp
            ),
            institutions,
        )

    return find


def _name_fulltext_affiliations(author, method, fulltext, institutions):
    for name in sorted(author.aliases, key=len, reverse=True):
        if aff := method(name, institutions):
            return aff
    else:
        return None


def find_fulltext_affiliations(paper, fulltext, institutions):
    if fulltext is None:
        return None

    doc = make_document_from_layout(fulltext)
    superscripts = classify_superscripts(doc)

    methods = [
        find_fulltext_affiliation_by_footnote(doc, superscripts),
        find_fulltext_affiliation_under_name(doc, 5),
        find_fulltext_affiliation_under_name(doc, 10000),
    ]

    for method in methods:
        aff = {
            aa.author: _name_fulltext_affiliations(
                aa.author, method, doc, institutions
            )
            or []
            for aa in paper.authors
        }
        if any(x for x in aff.values()):
            return aff
