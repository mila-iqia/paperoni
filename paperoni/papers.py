import json
import re
from collections import defaultdict
from hashlib import md5

from hrepr import HTML

from .researchers import Researchers
from .utils import T, asciiify, download, join, normalize as _norm, print_field

H = HTML()


class Papers:
    """Collection of papers."""

    # Fields that we fetch when querying papers.
    fields = [
        "Id",
        "FamId",
        "AA.AuN",
        "AA.DAuN",
        "AA.AuId",
        "AA.S",
        "AA.DAfN",
        "D",
        "Y",
        "Ti",
        "DN",
        "S",
        "IA",
        "CC",
        "Pt",
        "F.FN",
        "F.FId",
        "J.JN",
        "J.JId",
        "C.CN",
        "C.CId",
        "VFN",
        "VSN",
        "BT",
        "BV",
        "PB",
        "FP",
        "LP",
        "I",
        "V",
    ]

    def __init__(self, papers, researchers=None, filename=None):
        if isinstance(papers, list):
            self.papers = {paper.pid: paper for paper in papers}
            self.excluded = {}
        else:
            self.papers = {
                int(id): Paper(paper, researchers)
                for id, paper in papers.items()
                if paper
            }
            self.excluded = {
                int(id) for id, paper in papers.items() if not paper
            }
        self.researchers = researchers or Researchers({})
        self.filename = filename

    def __iter__(self):
        return iter(self.papers.values())

    def __contains__(self, paper):
        return paper.pid in self.papers

    def __len__(self):
        return len(self.papers)

    def excludes(self, paper):
        return paper.pid in self.excluded

    def add(self, paper):
        self.excluded.discard(paper.pid)
        self.papers[paper.pid] = paper

    def exclude(self, paper):
        if paper.pid in self.papers:
            del self.papers[paper.pid]
        self.excluded.add(paper.pid)

    def sorted(self, field="date", desc=False):
        results = list(
            sorted(self.papers.values(), key=lambda paper: getattr(paper, field))
        )
        if desc:
            results.reverse()
        # return Papers(results, self.researchers)
        return results

    def group(self):
        """Group versions of the same paper using family id."""
        groups = defaultdict(list)
        for paper in self:
            groups[paper.fid].append(paper)
        results = []
        for fid, group in groups.items():
            group.sort(key=lambda p: p.date, reverse=True)
            group[0].latest = True

            main = [p for p in group if p.pid == fid]
            if not main:
                main = group[:1]
            (main,) = main

            group.remove(main)
            main.other_versions = group
            results.append(main)
        return Papers(results, researchers=self.researchers)

    def filter(self, fn):
        """Filter papers based on some condition."""
        return Papers([p for p in self if fn(p)])

    def save(self):
        if self.filename is None:
            raise Exception("No file to save the papers.")
        data = {id: paper.data for id, paper in self.papers.items()}
        data.update({id: False for id in self.excluded})
        text = json.dumps(data, indent=4)
        with open(self.filename, "w") as file:
            file.write(text)

    def _q_author(self, papers, author):
        if isinstance(author, int):
            return [
                p
                for p in papers
                if any(auth.aid == author for auth in p.authors)
            ]
        else:
            author = _norm(author)
            return [
                p
                for p in papers
                if any(author == _norm(auth.name) for auth in p.authors)
            ]

    def _q_paper_id(self, papers, paper_id):
        return [p for p in papers if p.pid == paper_id]

    def _q_title(self, papers, title):
        query = _norm(title)
        query = re.split(r"\W+", query)
        return [p for p in papers if all(q in _norm(p.title) for q in query)]

    def _q_words(self, papers, query):
        query = _norm(query)
        query = re.split(r"\W+", query)
        return [
            p
            for p in papers
            if all(q in _norm(p.title) for q in query)
            or all(q in _norm(p.abstract) for q in query)
        ]

    def _q_institution(self, papers, inst):
        inst = _norm(inst)
        return [
            p
            for p in papers
            if any(_norm(auth.affiliation) == inst for auth in p.authors)
        ]

    def _q_venue(self, papers, venue):
        venue = _norm(venue)
        return [
            p
            for p in papers
            if (p.conference and _norm(p.conference).startswith(venue))
            or (p.journal and _norm(p.journal) == venue)
        ]

    def _q_keywords(self, papers, query):
        if not query:
            return papers
        query = {_norm(kw) for kw in query}
        return [p for p in papers if set(p.keywords) & query]

    def _q_daterange(self, papers, r):
        start, end = r
        if start is None and end is None:
            return papers
        return [
            p
            for p in papers
            if (start is None or p.date >= start)
            and (end is None or p.date <= end)
        ]

    def query(self, q, **params):
        """Run a query with the given parameters.

        Arguments:
            q: A query dictionary with any or all of these keys, which
               are combined using the AND operator.
                * author: Search for an author.
                * title: Words in the title.
                * words: Words in the title or abstract.
                * institution: Search papers from an institution.
                * keywords: List of paper keywords.
                * daterange: A tuple of (startdate, enddate), either of
                  which can be None.
            params: Parameters for the query such as limit and offset.
        """
        results = list(self.papers.values())
        for k, v in q.items():
            if v is None:
                continue
            method_name = f"_q_{k}"
            results = getattr(self, method_name)(results, v)
        return results


class Paper:
    """Represents a paper."""

    def __init__(self, data, researchers):
        self.data = data
        self.pid = data["Id"]
        self.fid = data.get("FamId", self.pid)
        self.title = data["DN"]
        self.date = data["D"]
        self.year = data["Y"]
        self.abstract = data["abstract"]

        authors = {}
        for auth_data in self.data["AA"]:
            aid = auth_data["AuId"]
            if aid in authors:
                authors[aid].affiliations.append(auth_data["DAfN"])
            else:
                authors[aid] = Author(
                    data=auth_data,
                    role=researchers
                    and researchers.find(aid).status_at(self.data["D"]),
                    researcher=researchers and researchers.find(aid),
                )

        self.authors = list(authors.values())
        self.links = Links(self.data.get("S", []))
        self.venue = data.get("BV", None)
        self.venue_fullname = data.get("VFN", None)
        self.venue_abbr = data.get("VSN", self.venue)
        if self.conference:
            self.venue_abbr += f' {self.data["Y"]}'

    @property
    def journal(self):
        if "J" in self.data:
            return self.data["J"]["JN"]
        else:
            return None

    @property
    def conference(self):
        if "C" in self.data:
            return self.data["C"]["CN"] + str(self.data["Y"])
        else:
            return None

    @property
    def keywords(self):
        return [k["FN"] for k in self.data.get("F", [])]

    @property
    def citations(self):
        cit = self.data["CC"]
        for p in getattr(self, "other_versions", []):
            cit += p.data["CC"]
        return cit

    def peer_review_status(self):
        """Returns a code representing peer review status.

        This uses heuristics and may not be fully accurate.

        * 0 -> preprint
        * 1 -> published in a conference or journal
        """
        no = ["arxiv", "biorxiv"]
        j = self.journal
        if j and any(j.startswith(entry) for entry in no):
            return 0
        return 1

    def type(self):
        bv = self.data.get("BV", "").lower()
        if "workshop" in bv:
            return ("workshop",)
        elif "symposium" in bv:
            return ("symposium",)
        else:
            if self.peer_review_status():
                subtype = "published"
            else:
                subtype = "preprint"
            return ("paper", subtype)

    def format_term(self):
        """Print the paper on the terminal."""
        print_field("Title", T.bold(self.title))
        print_field("Authors", ", ".join(auth.name for auth in self.authors))
        print_field("Date", self.date)
        if self.conference:
            print_field("Conference", self.venue)
        elif self.journal:
            print_field("Journal", self.venue)
        print_field("URL", self.links.best())

    def format_term_long(self):
        """Print the paper in long form on the terminal.

        Long form includes abstract, affiliations, keywords, number of
        citations.
        """
        print_field("Title", self.title)
        print_field("Authors", "")
        for auth in self.authors:
            print(f" * {auth.name:30} {auth.affiliation}")
        print_field("Abstract", self.abstract)
        print_field("Date", self.date)
        if self.conference:
            print_field("Conference", self.venue)
        elif self.journal:
            print_field("Journal", self.venue)
        print_field(
            "Keywords", ", ".join(k["FN"] for k in self.data.get("F", []))
        )
        print_field("Sources", "")
        for link in self.links.sorted(link_sort_key):
            print(f"  {T.bold_green(link.type)} {link.url}")
        print_field("Citations", self.citations)

    @property
    def reference_string(self):
        """Return a reference string for the paper, for bibtex.

        The reference is formatted as "{author}{year}-{word}{number}" where:

        * author: The last name of the first author if 10 authors or less, the
          string "collab" if more than 10 authors.
        * year: The year of publication.
        * word: The longest word in the title.
        * number: A pseudo-random number between 0 and 99, computed from the
          hash of the paper's attributes.

        Collisions are possible, but unlikely. The greatest chance of collision
        would be between the arxiv and peer-published versions of the same
        paper (~1% chance), but this is unlikely to present a major issue.
        """
        words = [w.lower() for w in re.split(r"\W", self.title)]
        ws = sorted(words, key=len, reverse=True)
        w = list(ws)[0]
        if len(self.authors) > 10:
            auth = "collab"
        else:
            auth = re.split(r"\W", self.authors[0].name)[-1].lower()
        h = md5(
            json.dumps(
                [
                    self.data.get("Ti", None),
                    self.data.get("AA", None),
                    self.data.get("BV", None),
                    self.data.get("D", None),
                ]
            ).encode()
        ).hexdigest()
        h = int(h, base=16) % 100
        identifier = f"{auth}{self.year}-{w}{h}"
        return asciiify(identifier)

    def download_pdf(self, filename=None):
        """Download the PDF in the given file.

        If no filename is given, the PDF is downloaded into
        {self.reference_string}.pdf.

        Returns:
            True if there was a PDF to download, False if not.
        """
        pdf = self.links.best("pdf")
        if filename is None:
            filename = f"{self.reference_string}.pdf"
        if pdf:
            download(pdf, filename=filename)
            return True
        else:
            return False

    def bibtex(self):
        """Return a bibtex entry for the paper.

        The name for the reference is self.reference_string.
        """
        author_names = [auth.name for auth in self.authors]
        author = "".join(map(str, join(author_names, lastsep=" and ")))

        entries = {
            "author": author,
            "title": self.title,
            "year": self.year,
        }

        bv = self.data.get("BV", None)
        bt = self.data.get("BT", None)

        if bt == "a":
            entry_type = "article"
            entries["booktitle"] = bv

        elif bt == "p":
            entry_type = "inproceedings"
            entries["booktitle"] = bv

        elif bt == "b":
            entry_type = "book"

        elif bt == "c":
            entry_type = "inbook"

        else:
            return None

        # Other fields
        fp = self.data.get("FP", None)
        lp = self.data.get("LP", None)
        if fp and lp:
            entries["pages"] = f"{fp}-{lp}"

        entries["publisher"] = self.data.get("PB", None)
        entries["volume"] = self.data.get("V", None)
        entries["number"] = self.data.get("I", None)

        entries = ",\n".join(
            f"    {k} = {{{v}}}" for k, v in entries.items() if v is not None
        )
        result = f"@{entry_type}{{{self.reference_string},\n{entries}\n}}"
        # bibtex doesn't like unicode
        result = asciiify(result)
        return result


class Author:
    """Represents the author of a paper."""

    def __init__(self, data, role, researcher):
        self.aid = data["AuId"]
        self.name = data["DAuN"]
        self.affiliations = [data["DAfN"]]
        self.role = role
        self.data = data
        # This is the Researcher instance for this author.
        self.researcher = researcher

    @property
    def affiliation(self):
        return self.affiliations[0] if self.affiliations else None


class Links:
    """Collection of links for a paper."""

    def __init__(self, links):
        self.links = [Link(lnk) for lnk in links]

    def __iter__(self):
        return iter(self.links)

    def seek(self, prop):
        for lnk in self.links:
            if lnk.has(prop):
                return lnk
        else:
            return None

    def sorted(self, sortkey):
        return list(sorted(self.links, key=sortkey))

    def best(self, type=None):
        """Return the "best" URL of a given type.

        Links to conference/journal pages are favored.
        """

        def chk(t):
            if type is None:
                return True
            elif type.startswith("~"):
                return t != type[1:]
            else:
                return t == type

        links = [lnk for lnk in self.sorted(link_sort_key) if chk(lnk.type)]
        return links[0].url if links else None


_link_type_map = {
    None: "?",
    1: "html",
    2: "text",
    3: "pdf",
    4: "doc",
    5: "ppt",
    6: "xls",
    7: "ps",
    999: "other",
}


# TODO: make this database extensible
_link_properties = {
    r".*arxiv": {"archive", "unreliable", "open"},
    r".*biorxiv": {"archive", "unreliable", "open"},
    r"openreview\.net": {"review", "unreliable", "open"},
    r"dblp": {"unreliable"},
    r"papers\.nips\.cc": {"best"},
    r"aaai\.org/ojs": {"reliable"},
    r"iclr\.cc": {"reliable"},
    r".*ijcnlp": {"reliable"},
    r"ijcai\.org": {"reliable"},
    r"nips\.cc": {"good"},
    r".*proceedings": {"good"},
    r".*article": {"decent"},
}


class Link:
    """Represents a link to a resource."""

    def __init__(self, data):
        self.type = _link_type_map.get(data.get("Ty", None), "???")
        self.url = data["U"]
        self.properties = set()
        for expr, props in _link_properties.items():
            if re.match(r"https?://" + expr, self.url):
                self.properties.update(props)

    def has(self, prop):
        return prop in self.properties

    def __str__(self):
        return self.url


def link_sort_key(lnk):
    typ = 0 if lnk.type == "html" else 1
    prio = {
        "best": 4,
        "reliable": 3,
        "good": 2,
        "decent": 1,
        "unreliable": -2,
        "archive": -3,
    }
    value = 0
    for prop in lnk.properties:
        new = prio.get(prop, 0)
        if abs(new) > abs(value):
            value = new
    return (typ, -value)
