import re
import unicodedata

from ...config import papconf
from ...fulltext.pdfanal import (
    classify_superscripts,
    normalize,
    undertext,
)
from ...model import Institution, InstitutionCategory


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
