import re

from coleo import Argument as Arg, default, tooled

from ..config import get_config
from ..io import PapersFile, ResearchersFile
from ..papers import Papers
from ..query import QueryManager


def _date(x, ending):
    if x is None:
        return None
    elif re.match(r"^[0-9]+$", x):
        return f"{x}-{ending}"
    else:
        return x


@tooled
def search_ext():

    # File containing the collection
    # [alias: -c]
    collection: Arg & PapersFile = default(None)

    # Researchers file (JSON)
    # [alias: -r]
    researchers: Arg & ResearchersFile = default(None)

    return search(collection=collection, researchers=researchers)


def join(parts):
    if parts is None or isinstance(parts, str):
        return parts
    else:
        return " ".join(parts)


@tooled
def search(collection=None, researchers=None):

    # Microsoft Cognitive API key
    key: Arg & str = default(get_config("key"))

    # [alias: -v]
    # Verbose output
    verbose: Arg & bool = default(False)

    # [group: search]
    # Search using a specific paper ID
    paper_id: Arg & int = default(None)

    # [group: search]
    # [alias: -t]
    # [nargs: *]
    # Search words in the title
    title: Arg & str = default(None)
    title = join(title)

    # [group: search]
    # [alias: -a]
    # [nargs: *]
    # Search for an author
    author: Arg & str = default(None)
    author = join(author)
    if author and re.match(r"^[0-9]+$", author):
        author = int(author)

    # [group: search]
    # [alias: -w]
    # [nargs: *]
    # Search words in the title or abstract
    words: Arg & str = default(None)
    words = join(words)

    # [group: search]
    # [alias: -k]
    # [nargs: *]
    # Search for keywords
    keywords: Arg & str = default([])
    keywords = [k.replace("_", " ") for k in keywords]

    # [group: search]
    # [alias: -i]
    # [nargs: *]
    # Search papers from institution
    institution: Arg & str = default(None)
    institution = join(institution)

    # [group: search]
    # Search papers from a specific conference or journal
    venue: Arg & str = default(None)

    # [group: search]
    # [nargs: *]
    # Researcher status(es) to filter for
    status: Arg = default([])

    # [group: search]
    # [alias: -y]
    # Year
    year: Arg & int = default(None)

    # [group: search]
    # Start date (yyyy-mm-dd or yyyy)
    start: Arg = default(str(year) if year is not None else None)
    start = _date(start, ending="01-01")

    # [group: search]
    # End date (yyyy-mm-dd or yyyy)
    end: Arg = default(str(year) if year is not None else None)
    end = _date(end, ending="12-31")

    # [group: search]
    # Sort by most recent
    recent: Arg & bool = default(False)

    # [group: search]
    # Sort by most cited
    cited: Arg & bool = default(False)

    # Group multiple versions of the same paper
    group: Arg & bool = default(False)

    # [group: search]
    # [negate: Do not list symposiums]
    # List symposiums
    symposium: Arg & bool = default(None)

    # [group: search]
    # [negate: Do not list workshops]
    # List workshops
    workshop: Arg & bool = default(None)

    # [group: search]
    # Number of papers to fetch (default: 100)
    limit: Arg & int = default(None)

    # [group: search]
    # Search offset
    offset: Arg & int = default(0)

    if researchers:
        qs = []
        for researcher in researchers:
            if not researcher.ids:
                continue
            for role in researcher.with_status(*status):
                qs.append(
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "author": researcher.ids,
                        "words": words,
                        "keywords": keywords,
                        "institution": institution,
                        "venue": venue,
                        "daterange": (role.begin, role.end),
                    }
                )

    else:
        qs = [
            {
                "paper_id": paper_id,
                "title": title,
                "author": author,
                "words": words,
                "keywords": keywords,
                "institution": institution,
                "venue": venue,
                "daterange": (start, end),
            }
        ]

    papers = []

    if collection is not None:
        for q in qs:
            if verbose:
                vq = {k: v for k, v in q.items() if v is not None}
                print(f"Querying: {vq} ...")
            papers.extend(collection.query(q))
        papers = Papers(papers, researchers)

    else:
        qm = QueryManager(key)

        for q in qs:
            if recent:
                orderby = "D:desc"
            elif cited:
                orderby = "CC:desc"
            else:
                orderby = None

            if verbose:
                vq = {k: v for k, v in q.items() if v is not None}
                print(f"Querying: {vq} ...")
            papers.extend(
                qm.query(
                    q,
                    attrs=",".join(Papers.fields),
                    orderby=orderby,
                    count=limit or 100,
                    offset=offset,
                    verbose=verbose,
                )
            )
            if verbose:
                print(f"Number of results: {len(papers)}")

        papers = Papers({p["Id"]: p for p in papers}, researchers)

    if group:
        papers = papers.group()

    if workshop is True:
        papers = papers.filter(lambda p: p.type()[0] == "workshop")
    elif workshop is False:
        papers = papers.filter(lambda p: p.type()[0] != "workshop")

    if symposium is True:
        papers = papers.filter(lambda p: p.type()[0] == "symposium")
    elif symposium is False:
        papers = papers.filter(lambda p: p.type()[0] != "symposium")

    # We need to re-sort the papers if there was more than one query
    if collection is not None or len(qs) > 1:
        if recent:
            papers = papers.sorted("date", desc=True)
        elif cited:
            papers = papers.sorted("citations", desc=True)

    if collection is not None:
        if offset:
            papers = papers[offset:]
        if limit:
            papers = papers[:limit]

    return papers
