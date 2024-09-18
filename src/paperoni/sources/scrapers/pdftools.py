import json
import re
import subprocess
import unicodedata
from types import SimpleNamespace

import requests

from ...config import papconf
from ...model import Institution, InstitutionCategory
from ...utils import download
from ..acquire import readpage
from .pdfanal import (
    classify_superscripts,
    make_document_from_layout,
    normalize,
    undertext,
)


class PDF:
    def __init__(self, link, cache_policy="use"):
        self.link = link
        self.cache_policy = cache_policy

        lnk = link.link.replace("/", "__")
        if not lnk.endswith(".pdf"):
            lnk = f"{lnk}.pdf"

        self.pdf_path = papconf.paths.cache / link.type / lnk

        if len(str(self.pdf_path)) > 255:
            # Weird stuff happens if this is true, so we just ignore it I guess?
            self.pdf_path = self.data_path = self.text_path = self.meta_path = (
                None
            )
            self.meta = {"failure": "bad_path"}
        else:
            self.data_path = self.pdf_path.with_suffix(".data")
            self.text_path = self.pdf_path.with_suffix(".txt")
            self.meta_path = self.pdf_path.with_suffix(".json")

            if self.meta_path.exists():
                self.meta = json.loads(self.meta_path.read_text())
            else:
                self.meta = {}

        self.last_failure = self.meta.get("failure", None)

    def get_url(self):
        link = self.link

        match link.type:
            case "arxiv":
                return f"https://export.arxiv.org/pdf/{link.link}.pdf"
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

    def acquire_and_process(self):
        pdf = self.pdf_path
        if not pdf:
            return False

        pdf.parent.mkdir(parents=True, exist_ok=True)

        if not pdf.exists() and self.cache_policy == "no_download":
            return False

        if not pdf.exists() or self.cache_policy == "force":
            if self.last_failure not in [None, "anonymous"]:
                print(
                    f"Skip {self} because of last failure: {self.last_failure}"
                )
                return False
            url = self.get_url()
            if url is None:
                return False
            try:
                download(filename=pdf, url=url)
            except requests.exceptions.SSLError:
                print(f"failed to download pdf file for {self}")
                self.clear(failure="ssl-error")
                return False

        # With metadata
        outcome = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf), str(self.data_path)],
            capture_output=True,
        )
        if outcome.returncode != 0:
            print(f"pdftotext failed to process pdf file for {self}")
            self.clear(failure="invalid-pdf")
            return False

        if not self.data_path.stat().st_size:
            self.pdf_path.unlink()
            self.data_path.unlink()
            self.clear(failure="empty")
            return False

        # Without
        outcome = subprocess.run(
            ["pdftotext", str(pdf), str(self.text_path)],
            capture_output=True,
        )
        # Remove newlines between words
        self.text_path.write_text(
            re.sub(
                string=self.text_path.read_text(),
                pattern=r"(\w) *\n *(\w)",
                repl=r"\1 \2",
            )
        )
        return True

    def get_fulltext(self, fulldata=True):
        if not self.pdf_path:
            return None

        if fulldata:
            target = self.data_path
        else:
            target = self.text_path

        if target.exists():
            if self.cache_policy != "force":
                return target.read_text()
        elif self.cache_policy == "only":
            return None

        if self.acquire_and_process():
            return target.read_text()
        else:
            return None

    def get_document(self):
        fulltext = self.get_fulltext()
        if not fulltext:
            return None
        doc = make_document_from_layout(fulltext)
        for line in doc.parts:
            if line.ymin < 1:
                # First page
                if re.search(
                    pattern="anonymous author",
                    string=line.text,
                    flags=re.IGNORECASE,
                ):
                    # Throw away the data; a later download might have the author info
                    print("Anonymous authors; throwing away.")
                    self.clear(failure="anonymous")
                    return None
            else:
                break
        return doc

    def clear(self, failure=None):
        self.write_meta(failure=failure)
        self.pdf_path.unlink(missing_ok=True)
        self.data_path.unlink(missing_ok=True)

    def write_meta(self, **data):
        self.meta.update(data)
        self.meta_path.write_text(json.dumps(data, indent=4))

    def __str__(self):
        return f"{self.link.type}:{self.link.link}"


def recognize_known_institution(entry, institutions):
    normalized = unicodedata.normalize("NFKC", entry.strip().strip(","))
    if normalized and normalized in institutions:
        return institutions[normalized]
    return None


def recognize_unknown_institution(entry):
    patterns = papconf.institution_patterns
    if not patterns or not entry or "@" in entry:
        return None
    for defn in patterns:
        pattern = defn.pattern
        category = defn.category
        m = re.match(pattern=pattern, string=entry, flags=re.IGNORECASE)
        if m:
            return Institution(
                name=entry,
                aliases=[],
                category=getattr(InstitutionCategory, category),
            )
    else:
        return None


def recognize_institutions(lines, institutions):
    lines = list(lines)
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

    name = re.sub(string=name, pattern=r"[(){}\[\]]", repl="")

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


def _name_fulltext_affiliations(aliases, method, doc, institutions):
    aliases = list(sorted(aliases, key=len, reverse=True))
    for name in aliases:
        if aff := method(name, institutions):
            return aff
    else:
        return method(initialize(aliases[0]), institutions, regex=True)


def find_fulltext_affiliations(paper, doc, institutions):
    if doc is None:
        return None

    methods = [
        find_fulltext_affiliation_by_footnote(
            doc,
            superscripts=classify_superscripts(doc, lenient=False),
        ),
        find_fulltext_affiliation_by_footnote(
            doc,
            superscripts=classify_superscripts(doc, lenient=True),
        ),
        find_fulltext_affiliation_under_name(doc, 5),
        find_fulltext_affiliation_under_name(doc, 10000),
    ]

    results = []

    authors = {}

    for aa in paper.authors:
        if aa.author:
            apos = aa.author_position
            aliases = aa.author.aliases
            maxl = max(map(len, aliases))
            if authors.get(apos, [0])[0] < maxl:
                authors[apos] = (maxl, aa.author, aliases)

    authors = sorted(authors.items(), key=lambda x: x[0])

    for i, method in enumerate(methods):
        aff = {
            author: _name_fulltext_affiliations(
                aliases, method, doc, institutions
            )
            or []
            for _, (_, author, aliases) in authors
        }
        score = sum(
            (
                0
                if len(afflist) == 0
                else 1
                if len(afflist) <= 3
                else 0
                if len(afflist) <= 5
                else -1
            )  # Suspiciously too many affiliations
            for afflist in aff.values()
        )
        results.append((score, -i, aff))

    results.sort(reverse=True)
    return results[0][-1]
