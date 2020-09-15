import re

from coleo import Option, default, tooled

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
    collection: Option & PapersFile = default(None)

    # Researchers file (JSON)
    # [alias: -r]
    researchers: Option & ResearchersFile = default(None)

    return search(collection=collection, researchers=researchers)


def join(parts):
    if parts is None or isinstance(parts, str):
        return parts
    else:
        return " ".join(parts)


@tooled
def search(collection=None, researchers=None):

    # Microsoft Cognitive API key
    key: Option & str = default(get_config("key"))

    # [alias: -v]
    # Verbose output
    verbose: Option & bool = default(False)

    # [group: search]
    # Search using a specific paper ID
    paper_id: Option & int = default(None)

    # [group: search]
    # [alias: -t]
    # [nargs: *]
    # Search words in the title
    title: Option & str = default(None)
    title = join(title)

    # [group: search]
    # [alias: -a]
    # [nargs: *]
    # [action: append]
    # Search for an author
    author: Option & str = default([])
    author = [join(a) for a in author]
    author = [int(a) if re.match(r"^[0-9]+$", a) else a for a in author]

    # [group: search]
    # [alias: -w]
    # [nargs: *]
    # Search words in the title or abstract
    words: Option & str = default(None)
    words = join(words)

    # [group: search]
    # [alias: -k]
    # [nargs: *]
    # [action: append]
    # Search for keywords
    keywords: Option & str = default([])
    keywords = [join(k) for k in keywords]

    # [group: search]
    # [alias: -i]
    # [nargs: *]
    # Search papers from institution
    institution: Option & str = default(None)
    institution = join(institution)

    # [group: search]
    # Search papers from a specific conference or journal
    venue: Option & str = default(None)

    # [group: search]
    # [nargs: *]
    # Researcher status(es) to filter for
    status: Option = default([])

    # [group: search]
    # [alias: -y]
    # Year
    year: Option & int = default(None)

    # [group: search]
    # Start date (yyyy-mm-dd or yyyy)
    start: Option = default(str(year) if year is not None else None)
    start = _date(start, ending="01-01")

    # [group: search]
    # End date (yyyy-mm-dd or yyyy)
    end: Option = default(str(year) if year is not None else None)
    end = _date(end, ending="12-31")

    # [group: search]
    # Sort by most recent
    recent: Option & bool = default(False)

    # [group: search]
    # Sort by most cited
    cited: Option & bool = default(False)

    # Group multiple versions of the same paper
    group: Option & bool = default(False)

    # [group: search]
    # [false-options]
    # [false-options-doc: Do not list symposiums]
    # List symposiums
    symposium: Option & bool = default(None)

    # [group: search]
    # [false-options]
    # [false-options-doc: Do not list workshops]
    # List workshops
    workshop: Option & bool = default(None)

    # [group: search]
    # Number of papers to fetch (default: 100)
    limit: Option & int = default(None)

    # [group: search]
    # Search offset
    offset: Option & int = default(0)

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
