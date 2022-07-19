import re
import shutil
import textwrap

from blessed import Terminal
from ovld import ovld

from paperoni.sources.model import Author, DatePrecision, Paper, from_dict

T = Terminal()
tw = shutil.get_terminal_size((80, 20)).columns


link_generators = {
    "arxiv": {
        "abstract": "https://arxiv.org/abs/{}",
        "pdf": "https://arxiv.org/pdf/{}.pdf",
    },
    "pubmed": {
        "abstract": "https://pubmed.ncbi.nlm.nih.gov/{}",
    },
    "pmc": {
        "abstract": "https://www.ncbi.nlm.nih.gov/pmc/articles/{}",
    },
    "doi": {
        "abstract": "https://doi.org/{}",
    },
    "openreview": {
        "abstract": "https://openreview.net/forum?id={}",
        "pdf": "https://openreview.net/pdf?id={}",
    },
    "dblp": {"abstract": "https://dblp.uni-trier.de/rec/{}"},
    "semantic_scholar": {
        "abstract": "https://www.semanticscholar.org/paper/{}"
    },
}


class QueryError(Exception):
    pass


class MutuallyExclusiveError(RuntimeError):
    """Exception raised when mutually exclusive parameters are used in queries."""

    def __init__(self, *args):
        self.args = args

    def __str__(self):
        return "Mutually exclusive parameters: " + " vs ".join(
            self._param_to_str(arg) for arg in self.args
        )

    def _param_to_str(self, param):
        return param if isinstance(param, str) else f"({', '.join(param)})"


def print_field(title, contents, bold=False):
    """Prints a line that goes 'title: contents', nicely formatted."""
    contents = textwrap.fill(f"{title}: {contents}", width=tw)[len(title) + 2 :]
    title = T.bold_cyan(f"{title}:")
    contents = T.bold(contents) if bold else contents
    print(title, contents)


def expand_links(links):
    pref = [
        "arxiv.abstract",
        "arxiv.pdf",
        "pubmed.abstract",
        "openreview.abstract",
        "openreview.pdf",
        "pmc.abstract",
        "dblp.abstract",
        "pdf",
        "doi.abstract",
        "html",
        "semantic_scholar.abstract",
        "corpusid",
        "mag",
        "xml",
        "patent",
        "unknown",
        "unknown_",
    ]
    results = []
    for link in links:
        if link.type in link_generators:
            results.extend(
                (f"{link.type}.{kind}", url.format(link.link))
                for kind, url in link_generators[link.type].items()
            )
        else:
            results.append((link.type, link.link))
    results.sort(key=lambda pair: pref.index(pair[0]) if pair[0] in pref else 1)
    return results


def format_term(self):
    """Print the paper on the terminal."""
    print_field("Title", T.bold(self.title))
    print_field("Authors", ", ".join(auth.name for auth in self.authors))
    for release in self.releases:
        print_field(
            "Date", DatePrecision.format(release.date, release.date_precision)
        )
        print_field("Venue", release.venue.name)
    if self.links:
        print_field("URL", expand_links(self.links)[0][1])


@ovld
def display(d: dict):
    display(from_dict(d))


@ovld
def display(paper: Paper):
    """Print the paper in long form on the terminal.

    Long form includes abstract, affiliations, keywords, number of
    citations.
    """
    print_field("Title", paper.title)
    print_field("Authors", "")
    for auth in paper.authors:
        print(
            f" * {auth.name:30} {', '.join(aff.name for aff in auth.affiliations)}"
        )
    print_field("Abstract", paper.abstract)
    for release in paper.releases:
        print_field(
            "Date", DatePrecision.format(release.date, release.date_precision)
        )
        print_field("Venue", release.venue.name)
    print_field("Topics", ", ".join(t.name for t in paper.topics))
    print_field("Sources", "")
    for typ, link in expand_links(paper.links):
        print(f"  {T.bold_green(typ)} {link}")
    print_field("Citations", paper.citation_count)


@ovld
def display(author: Author):
    """Print an author on the terminal."""
    print_field("Name", T.bold(author.name))
    if author.affiliations:
        print_field("Affiliations", "")
        for affiliation in author.affiliations:
            print(f"* {affiliation.name}")
    if author.roles:
        print_field("Roles", "")
        for role in author.roles:
            print(
                f"* {role.institution.name:20} as {role.role:20} from {DatePrecision.day.format2(role.start_date)} to {role.end_date and DatePrecision.day.format2(role.end_date) or '-'}"
            )
    print_field("Links", "")
    for typ, link in expand_links(author.links):
        print(f"  {T.bold_green(typ):20} {link}")


url_extractors = {
    r"https?://[a-z.]*arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://[a-z.]*arxiv-vanity\.com/papers/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://(?:[^/]*)arxiv(?:[^/]*)\.cornell\.edu/abs/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://scirate\.com/arxiv/([0-9]{4}\.[0-9]+).*": "arxiv",
    r"https?://pubmed\.ncbi\.nlm\.nih\.gov/([^/]*)/": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pubmed/([^/]*)": "pubmed",
    r"https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/([^/]*)": "pmc",
    r"https?://europepmc.org/article/PMC/([^/]*)": "pmc",
    r"https?://(?:dx\.)?doi\.org/(.*)": "doi",
    r"https?://(?:www\.)?openreview\.net/(?:pdf\?|forum\?)id=(.*)": "openreview",
    r"https?://dblp.uni-trier.de/db/([^/]+)/([^/]+)/[^/]+\.html#(.*)": "dblp",
}


def url_to_id(url):
    for pattern, key in url_extractors.items():
        if m := re.match(pattern, url):
            lnk = "/".join(m.groups())
            return (key, lnk)
    return None


def canonicalize_links(links):
    links = {
        url_to_id(url := link["link"]) or (link["type"], url) for link in links
    }
    return [{"type": typ, "link": lnk} for typ, lnk in links]
