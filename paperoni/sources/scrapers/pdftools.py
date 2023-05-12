import re
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


class PDF:
    def __init__(self, link, cache_policy="use"):
        self.link = link
        self.cache_policy = cache_policy

        lnk = link.link.replace("/", "__")
        if not lnk.endswith(".pdf"):
            lnk = f"{lnk}.pdf"

        self.pdf_path = Path(config.get().paths.cache) / link.type / lnk
        self.data_path = self.pdf_path.with_suffix(".data")
        self.fulltext = self.get_fulltext()

    def get_url(self):
        link = self.link

        match link.type:
            case "arxiv":
                return f"https://arxiv.org/pdf/{link.link}.pdf"
            case "openreview":
                return f"https://openreview.net/pdf?id={link.link}"
            case "doi":
                data = readpage(
                    f"https://api.crossref.org/v1/works/{link.link}",
                    format="json",
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
                        return lnk["URL"]
                else:
                    return None
            case "pdf":
                return link.link
            case _:
                return None

    def get_fulltext(self):
        if len(str(self.pdf_path)) > 255:
            # Weird stuff happens if this is true, so we just ignore it I guess?
            return ""

        pdf = self.pdf_path
        data = self.data_path

        if data.exists():
            if self.cache_policy != "force":
                return data.read_text()
        elif self.cache_policy == "only":
            return None

        pdf.parent.mkdir(parents=True, exist_ok=True)

        if not pdf.exists() or self.cache_policy == "force":
            try:
                download(filename=pdf, url=self.get_url())
            except requests.exceptions.SSLError:
                return None

        subprocess.run(["pdftotext", "-bbox-layout", str(pdf), str(data)])

        if not data.stat().st_size:
            data.unlink()

        fulltext = data.read_text()
        if not fulltext:
            self.clear()
            return None

        return fulltext

    def clear(self):
        self.pdf_path.unlink(missing_ok=True)
        self.data_path.unlink(missing_ok=True)


triggers = {
    "Mila": (10, InstitutionCategory.academia),
    "MILA": (10, InstitutionCategory.academia),
    "Université": (6, InstitutionCategory.academia),
    "Universite": (6, InstitutionCategory.academia),
    "University": (6, InstitutionCategory.academia),
    "Polytechnique": (6, InstitutionCategory.academia),
    "Institute": (6, InstitutionCategory.unknown),
    "Department": (6, InstitutionCategory.unknown),
    "Research": (4, InstitutionCategory.unknown),
    "Montréal": (2, InstitutionCategory.academia),
    "Québec": (2, InstitutionCategory.academia),
    "Montreal": (2, InstitutionCategory.academia),
    "Quebec": (2, InstitutionCategory.academia),
}


def recognize_known_institution(entry, institutions):
    normalized = unicodedata.normalize("NFKC", entry.strip().strip(","))
    if normalized and normalized in institutions:
        return institutions[normalized]
    return None


def recognize_unknown_institution(entry):
    if (
        entry
        and any((trigger := t) in entry for t in triggers)
        and "@" not in entry
    ):
        return Institution(
            name=entry, aliases=[], category=triggers[trigger][1]
        )
    else:
        return None


def recognize_institutions(lines, institutions):
    affiliations = []
    for line in lines:
        if line.startswith(","):
            continue
        candidates = [line, *re.split(pattern=",|and|;|&", string=line)]
        for candidate in candidates:
            known = recognize_known_institution(candidate, institutions)
            if known and known not in affiliations:
                affiliations.append(known)

    if affiliations:
        return affiliations

    for line in lines:
        if line.startswith(","):
            continue
        unknown = recognize_unknown_institution(line)
        if unknown and unknown not in affiliations:
            affiliations.append(unknown)

    return affiliations


def find_fulltext_affiliation_by_footnote(doc, superscripts):
    def find(name, institutions, regex=False):
        key = None
        if regex:
            for k in superscripts:
                if re.search(string=k, pattern=normalize(name)):
                    key = k
                    break
        else:
            nname = normalize(name)
            if nname in superscripts:
                key = nname
        if key:
            return recognize_institutions(set(superscripts[key]), institutions)

    return find


def find_fulltext_affiliation_under_name(doc, extra_margin):
    def find(name, institutions, regex=False):
        return recognize_institutions(
            (
                line
                for utgrp in undertext(doc, name, extra_margin, regex)
                for line in utgrp
            ),
            institutions,
        )

    return find


def initialize(name):
    def i(part):
        return f"{part[0]}[a-z]*"

    parts = name.split()
    if len(parts) <= 1:
        return name
    else:
        first, *middles, last = parts
        new_parts = [
            i(first),
            " ",
            *[f"(?:{i(part)} )?" for part in middles],
            last,
        ]
        return "".join(new_parts)


def _name_fulltext_affiliations(author, method, fulltext, institutions):
    aliases = list(sorted(author.aliases, key=len, reverse=True))
    for name in aliases:
        if aff := method(name, institutions):
            return aff
    else:
        return method(initialize(aliases[0]), institutions, regex=True)


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

    results = []

    for i, method in enumerate(methods):
        aff = {
            aa.author: _name_fulltext_affiliations(
                aa.author, method, doc, institutions
            )
            or []
            for aa in paper.authors
            if aa.author
        }
        results.append((sum(1 for x in aff.values() if x), -i, aff))

    results.sort(reverse=True)
    return results[0][-1]
