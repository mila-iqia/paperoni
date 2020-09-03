import os
import shutil
import sys

from coleo import Argument as Arg, default, tooled
from hrepr import H

from ..io import PapersFile, ResearchersFile
from ..utils import group_by, join, normalize
from .searchutils import search

try:
    import bs4
except ImportError:
    bs4 = None


class Template:
    def __init__(self, filename):
        if bs4 is None:
            sys.exit(
                "BeautifulSoup must be installed for this feature.\n\n"
                "  pip install bs4"
            )

        if "#" in filename:
            self.filename, self.divid = name.split("#", 1)
        else:
            self.filename = filename
            self.divid = "paperoni-papers"

        self.contents = bs4.BeautifulSoup(
            open(self.filename).read(), features="html.parser"
        )
        self.elem = self.contents.find(id=self.divid)
        if self.elem is None:
            sys.exit(f"Could not find #{self.divid} in the template")

    def inject(self, contents):
        self.elem.clear()
        self.elem.append(bs4.BeautifulSoup(contents, features="html.parser"))

    def save(self, dest, prettify=False):
        if prettify:
            contents = self.contents.prettify()
        else:
            contents = str(self.contents)
        dest.write(contents)


@tooled
def format_paper(paper):
    # Show author affiliations
    show_affiliations: Arg & bool = default(False)

    # Show keywords
    show_keywords: Arg & bool = default(False)

    # Show the citation count
    show_citation_count: Arg & bool = default(False)

    # Property in the researchers file to use as the author's bio
    biofield: Arg & str = default("bio")

    # Maximum number of authors to display on a paper (default: 10)
    maxauth: Arg & int = default(10)

    affiliations = {}
    if show_affiliations:
        for auth in paper.authors:
            for aff in auth.affiliations:
                if aff not in affiliations:
                    affiliations[aff] = aff and (len(affiliations) + 1)
        if len(affiliations) == 1:
            affiliations[list(affiliations.keys())[0]] = ""

    def _domain(lnk):
        return lnk.split("/")[2]

    def _format_author(auth):
        bio = auth.researcher and auth.researcher.properties.get(biofield, None)
        if bio:
            authname = H.a["author-name"](auth.name, href=bio)
        else:
            authname = H.span["author-name"](auth.name)

        return H.span["author"](
            authname,
            [
                H.sup["author-affiliation"](affiliations[aff])
                for aff in auth.affiliations
                if aff in affiliations
            ],
        )

    lnk = paper.links.best("~pdf") or ""
    pdf = paper.links.best("pdf") or ""
    nauth = len(paper.authors)
    more = nauth - maxauth if nauth > maxauth else 0

    def _alsosee(p):
        common = (p.venue, " (", p.date, ")")
        lnk = p.links.best("pdf") or p.links.best("~pdf") or ""
        if getattr(p, "latest", False):
            return H.a["latest-on"]("[LATEST on ", *common, "]", href=lnk)
        else:
            return H.a["also-on"]("[Also on ", *common, "]", href=lnk)

    return H.div["paper"](
        H.div["title"](paper.title),
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
        H.div["keywords"](join(x["FN"] for x in paper.data["F"]))
        if show_keywords
        else "",
        H.div["extra"](
            H.span["venue"](paper.venue_abbr or "(venue unknown)"),
            " ",
            H.span["date"]("(", paper.date, ")"),
            " ",
            lnk and H.a["link"](f"{_domain(lnk)}", href=lnk),
            " ",
            pdf and H.a["link", "pdf-link"]("PDF", href=pdf),
            " ",
            [(_alsosee(p), " ") for p in getattr(paper, "other_versions", [])],
            ("[Citations: ", paper.citations , "]")
            if show_citation_count
            else "",
        ),
    )


@tooled
def command_html():
    """Generate html entries for a search."""

    # Researchers file (JSON)
    # [alias: -r]
    researchers: Arg & ResearchersFile = default(None)

    # Collection file (JSON)
    # [alias: -c]
    collection: Arg = default(None)
    if collection:
        collection = PapersFile(collection, researchers=researchers)

    # "year", "month" or "none" to separate entries by year or
    # month or to not separate them (default: year)
    headers: Arg & normalize = default("year")

    # File#divid to inject the HTML
    inject: Arg & Template = default(None)

    # HTML template
    template: Arg & Template = default(None)

    # Print the raw HTML, no template
    no_template: Arg & bool = default(False)

    if not no_template and template is None:
        template = Template(
            os.path.join(os.path.dirname(__file__), "default.html")
        )

    # Output file
    # [alias: -o]
    output: Arg = default(None)

    # Make no backup of the file specified with --inject
    no_backup: Arg = default(False)

    if inject and template:
        sys.exit("Cannot specify both --inject and --template")
    if inject and output:
        sys.exit("Cannot specify both --inject and --output")

    papers = search(collection=collection)

    results = []

    if headers == "none":
        for paper in papers:
            results.append(str(format_paper(paper)))
    else:
        if headers == "year":

            def sortkey(p):
                return p.year

        elif headers == "month":

            def sortkey(p):
                return p.date[:7]

        else:
            sys.exit(f"Invalid headers: {headers}")

        papers = group_by(papers, sortkey)
        for key, papers in sorted(papers.items(), reverse=True):
            grp = H.div["paper-group"](
                H.h3(key), [format_paper(paper) for paper in papers]
            )
            results.append(str(grp))

    results = "\n".join(results) + "\n"

    if output:
        out = open(output, "w")
    else:
        out = sys.stdout

    if template:
        template.inject(results)
        template.save(out)

    elif inject:
        if not no_backup:
            bk = f"{inject.filename}.bk"
            print(f"Backing up the file in {bk}")
            shutil.copy2(inject.filename, bk)
        inject.inject(results)
        inject.save(open(inject.filename, "w"))

    else:
        out.write(results)
