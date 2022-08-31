import shutil
import textwrap
from typing import Union

from blessed import Terminal
from hrepr import H
from ovld import ovld

from .db import schema as sch
from .model import Author, DatePrecision, Paper, Venue, from_dict

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
        venue = release.venue
        print_field(
            "Date", DatePrecision.format(venue.date, venue.date_precision)
        )
        print_field("Venue", venue.name)
    if self.links:
        print_field("URL", expand_links(self.links)[0][1])


@ovld
def display(d: dict):
    display(from_dict(d))


@ovld
def display(paper: Union[Paper, sch.Paper]):
    """Print the paper in long form on the terminal.

    Long form includes abstract, affiliations, keywords, number of
    citations.
    """
    print_field("Title", paper.title)
    print_field("Authors", "")
    for auth in paper.authors:
        if auth.author:
            print(
                f" * {auth.author.name:30} {', '.join(aff.name for aff in auth.affiliations)}"
            )
        else:
            print(T.bold_red("ERROR: MISSING AUTHOR"))
    print_field("Abstract", paper.abstract)
    print_field("Venue", "")
    for release in paper.releases:
        venue = release.venue
        d = DatePrecision.format(venue.date, venue.date_precision)
        v = venue.name
        print(f"  {T.bold_green(d)} {T.bold_magenta(release.status)} {v}")
    print_field("Topics", ", ".join(t.name for t in paper.topics))
    print_field("Sources", "")
    for typ, link in expand_links(paper.links):
        print(f"  {T.bold_green(typ)} {link}")
    print_field("Citations", paper.citation_count)


@ovld
def display(author: Author):
    """Print an author on the terminal."""
    print_field("Name", T.bold(author.name))
    if author.roles:
        print_field("Affiliations", "")
        for role in author.roles:
            print(
                f"* {role.institution.name:20} as {role.role:20} from {DatePrecision.day.format2(role.start_date)} to {role.end_date and DatePrecision.day.format2(role.end_date) or '-'}"
            )
    print_field("Links", "")
    for typ, link in expand_links(author.links):
        print(f"  {T.bold_green(typ):20} {link}")


@ovld
def display(venue: Venue):
    """Print a release on the terminal."""
    print_field("Venue", T.bold(venue.name))
    print_field("Series", T.bold(venue.series))
    print_field("Type", T.bold(venue.type))
    if venue.aliases:
        print_field("Aliases", "")
        for alias in venue.aliases:
            print(f"* {alias}")
    d = DatePrecision.format(venue.date, venue.date_precision)
    print_field("Date", d)
    print_field("Links", "")
    for typ, link in expand_links(venue.links):
        print(f"  {T.bold_green(typ):20} {link}")


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


@ovld
def html(paper: Union[Paper, sch.Paper]):
    show_affiliations = True
    show_keywords = True
    show_citation_count = True
    maxauth = 10

    affiliations = {}
    if show_affiliations:
        for auth in paper.authors:
            for aff in auth.affiliations:
                aff = aff.name
                if aff not in affiliations:
                    affiliations[aff] = aff and (len(affiliations) + 1)
        if len(affiliations) == 1:
            affiliations[list(affiliations.keys())[0]] = ""

    def _format_author(auth):
        bio = [
            f"https://mila.quebec/en/person/{l.link}"
            for l in auth.author.links
            if l.type == "bio"
        ]
        if bio:
            (bio,) = bio
            authname = H.a["author-name"](auth.author.name, href=bio)
        else:
            authname = H.span["author-name"](auth.author.name)

        return H.span["author"](
            authname,
            [
                H.sup["author-affiliation"](affiliations[aff.name])
                for aff in auth.affiliations
                if aff.name in affiliations
            ],
        )

    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0

    venues = H.div["venues"]
    for release in paper.releases:
        v = release.venue
        venues = venues(
            H.div["venue"](
                H.span["venue-date"](
                    DatePrecision.format(v.date, v.date_precision)
                ),
                H.span["venue-name"](v.name),
                H.span["venue-status"](release.status),
            )
        )

    def _domain(lnk):
        return lnk.split("/")[2]

    pdfs = [lnk for k, lnk in expand_links(paper.links) if "pdf" in lnk]

    return H.div["paper"](
        H.div["title"](H.a(paper.title, href=pdfs[0]) if pdfs else paper.title),
        H.div["authors"](
            join(
                [_format_author(auth) for auth in paper.authors[:maxauth]],
                lastsep=", " if more else " and ",
            ),
            f"... ({more} more)" if more else "",
        ),
        H.div["affiliations"](
            (H.sup["author-affiliation"](idx), H.span["affiliation"](aff), " ")
            for aff, idx in affiliations.items()
        )
        if show_affiliations
        else "",
        venues,
        H.div["keywords"](join(x.name for x in paper.topics))
        if show_keywords
        else "",
        H.div["extra"](
            H.a["link"](
                _domain(link) if typ == "html" else typ.replace("_", "-"),
                href=link,
            )
            for typ, link in expand_links(paper.links)
            if link.startswith("http")
        ),
        H.div(paper.citation_count, " citations")
        if paper.citation_count and show_citation_count
        else "",
    )
