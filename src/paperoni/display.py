import shutil
import textwrap

from blessed import Terminal
from ovld import ovld, recurse

from .model import Author, DatePrecision, Paper, Scored, Venue
from .model.merge import PaperWorkingSet
from .utils import expand_links_dict

T = Terminal()
terminal_width = shutil.get_terminal_size((80, 20)).columns


def print_field(title, contents, bold=False):
    """Prints a line that goes 'title: contents', nicely formatted."""
    contents = textwrap.fill(f"{title}: {contents}", width=terminal_width)[
        len(title) + 2 :
    ]
    title = T.bold_cyan(f"{title}:")
    contents = T.bold(contents) if bold else contents
    print(title, contents)


def expand_links(links):
    return [
        (x["type"], x.get("url", None) or x["link"]) for x in expand_links_dict(links)
    ]


@ovld
def display(d: dict):
    for k, v in d.items():
        print_field(k, v)


@ovld
def display(s: Scored):
    recurse(s.value)
    print_field("Score", s.score)


@ovld
def display(paper: Paper):
    """Print the paper in long form on the terminal.

    Long form includes abstract, affiliations, keywords.
    """
    print_field("Title", paper.title)
    print_field("Authors", "")
    for auth in paper.authors:
        if auth.author:
            print(
                f" * {auth.author.name:30} {'; '.join(aff.name for aff in auth.affiliations)}"
            )
        else:  # pragma: no cover
            print(T.bold_red("ERROR: MISSING AUTHOR"))
    print_field("Abstract", paper.abstract)
    print_field("Venue", "")
    for release in paper.releases:
        venue = release.venue
        d = DatePrecision.format(venue.date, venue.date_precision)
        v = ", ".join(
            part for part in [venue.short_name or venue.name, venue.volume] if part
        )
        print(f"  {T.bold_green(d)} {T.bold_magenta(release.status)} {v}")
    print_field("Topics", ", ".join(t.name for t in paper.topics))
    print_field("Sources", "")
    for typ, link in expand_links(paper.links):
        print(f"  {T.bold_green(typ)} {link}")
    if hasattr(paper, "citation_count"):
        print_field("Citations", paper.citation_count)
    if hasattr(paper, "excerpt"):
        before, match, after = paper.excerpt
        print_field("Excerpt", before + T.bold_red(match) + after)
    if paper.info:
        print_field("Info", "")
    for field, value in paper.info.items():
        print(f"  {T.bold_green(field)} {value}")


@ovld
def display(author: Author):
    """Print an author on the terminal."""
    print_field("Name", T.bold(author.name))
    if author.aliases:
        print_field("Aliases", ", ".join(author.aliases))
    if author.roles:
        print_field("Affiliations", "")
        for role in author.roles:
            print(
                f"* {role.role:20} {role.institution.name:40} from {DatePrecision.format(role.start_date, DatePrecision.day)} to {role.end_date and DatePrecision.format(role.end_date, DatePrecision.day) or '-'}"
            )
    print_field("Links", "")
    for link in author.links:
        print(f"  {T.bold_green(link.type):20} {link.link}")


@ovld
def display(venue: Venue):
    """Print a release on the terminal."""
    print_field(
        "Venue",
        ", ".join(
            map(
                T.bold,
                [part for part in [venue.short_name or venue.name, venue.volume] if part],
            )
        ),
    )
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


@ovld
def display(x: PaperWorkingSet):
    recurse(x.current)
    print_field("Versions", len(x.collected))


@ovld
def display(x: object):
    print(x)
