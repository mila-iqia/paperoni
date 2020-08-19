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


@tooled
def search(collection=None, researchers=None):

    # Microsoft Cognitive API key
    key: Arg & str = default(get_config("key"))

    # [alias: -v]
    # Verbose output
    verbose: Arg & bool = default(False)

    # [alias: -t]
    # [nargs: *]
    # Search words in the title
    title: Arg & str = default(None)
    title = title and " ".join(title)

    # [alias: -a]
    # [nargs: *]
    # Search for an author
    author: Arg & str = default(None)
    author = author and " ".join(author)
    if author and re.match(r"^[0-9]+$", author):
        author = int(author)

    # [alias: -w]
    # [nargs: *]
    # Search words in the title or abstract
    words: Arg & str = default(None)
    words = words and " ".join(words)

    # [alias: -k]
    # [nargs: *]
    # Search for keywords
    keywords: Arg & str = default([])
    keywords = [k.replace("_", " ") for k in keywords]

    # [alias: -i]
    # [nargs: *]
    # Search papers from institution
    institution: Arg & str = default(None)
    institution = institution and " ".join(institution)

    # Search papers from a specific conference or journal
    venue: Arg & str = default(None)

    # [nargs: *]
    # Researcher status(es) to filter for
    status: Arg = default([])

    # [alias: -y]
    # Year
    year: Arg & int = default(None)

    # Start date (yyyy-mm-dd or yyyy)
    start: Arg = default(str(year) if year is not None else None)
    start = _date(start, ending="01-01")

    # End date (yyyy-mm-dd or yyyy)
    end: Arg = default(str(year) if year is not None else None)
    end = _date(end, ending="12-31")

    # Sort by most recent
    recent: Arg & bool = default(False)

    # Sort by most cited
    cited: Arg & bool = default(False)

    # Number of papers to fetch (default: 100)
    limit: Arg & int = default(100)

    # Search offset
    offset: Arg & int = default(0)

    if researchers:
        qs = []
        for researcher in researchers:
            for role in researcher.with_status(*status):
                for rid in researcher.ids:
                    qs.append(
                        {
                            "title": title,
                            "author": rid,
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
                print(f"Querying: {q} ...")
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
                print(f"Querying: {q} ...")
            papers.extend(
                qm.query(
                    q,
                    attrs=",".join(Papers.fields),
                    orderby=orderby,
                    count=limit,
                    offset=offset,
                    verbose=verbose,
                )
            )
            if verbose:
                print(f"Number of results: {len(papers)}")

        papers = Papers({p["Id"]: p for p in papers}, researchers)

    # We need to re-sort the papers if there was more than one query
    if collection is not None or len(qs) > 1:
        if recent:
            papers = papers.sorted("D", desc=True)
        elif cited:
            papers = papers.sorted("CC", desc=True)

    return papers
