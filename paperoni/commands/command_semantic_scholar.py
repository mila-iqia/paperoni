from coleo import Option, default, tooled

from ..papers import Paper, Papers
from ..sources.semantic_scholar import SemanticScholarQueryManager
from .interactive import InteractiveCommands, default_commands

search_commands = InteractiveCommands("Enter a command", default="s")


@search_commands.register("s", "[s]kip")
def _s(self, paper, **_):
    """Skip and see the next paper"""
    return True


search_commands.update(default_commands)


def _to_microsoft(paper_data: dict):
    return {
        "Id": int(paper_data["paperId"], 16),
        "FamId": paper_data["paperId"],
        "Y": paper_data["year"],
        "D": "%04d-01-01" % (paper_data["year"] or 0),
        "Ti": paper_data["title"],
        "DN": paper_data["title"],
        "abstract": paper_data["abstract"],
        "CC": paper_data["citationCount"],
        "F": [{"FN": f} for f in (paper_data["fieldsOfStudy"] or ())],
        "J": {"JN": paper_data["venue"],},
        "S": [{"Ty": "1", "U": paper_data["url"]}],
        "VFN": paper_data["venue"],
        "VSN": paper_data["venue"],
        "BV": paper_data["venue"],
        "PB": paper_data["venue"],
        "AA": [
            {
                "AuN": author_dict["name"],
                "DAuN": author_dict["name"],
                "AuId": author_dict["authorId"],
                "DAfN": "",
            }
            for author_dict in paper_data["authors"]
        ],
    }


def join(parts):
    if parts is None or isinstance(parts, str):
        return parts
    else:
        return " ".join(parts)


@tooled
def search():
    # [alias: -v]
    # Verbose output
    verbose: Option & bool = default(False)

    # [group: search]
    # [positional: *]
    # Search for keywords
    keywords: Option & str = default([])
    keywords = [join(k) for k in keywords]

    # [group: search]
    # [alias: -a]
    # Search by author ID
    author: Option & str = default("")

    # [group: search]
    # Number of papers to fetch (default: 100)
    limit: Option & int = default(100)

    # [group: search]
    # Search offset
    offset: Option & int = default(0)

    if author and keywords:
        raise RuntimeError(
            "Please specify either keywords or author ID, but not both"
        )
    elif not author and not keywords:
        raise RuntimeError("Keywords or author ID required.")

    qm = SemanticScholarQueryManager()
    if verbose:
        print(
            "[semantic scholar search]",
            f"keywords: {keywords}," if keywords else f"author ID: {author},",
            f"limit: {limit}, offset: {offset}",
        )

    if keywords:
        papers = list(qm.search(keywords, limit=limit, offset=offset))
    else:
        papers = list(qm.author_papers(author, limit=limit, offset=offset))
    papers = [_to_microsoft(dct) for dct in papers]
    if verbose:
        print(f"Number of results: {len(papers)}")

    papers = Papers({p["Id"]: p for p in papers})
    return papers


@tooled
def command_semantic_scholar():
    """Query the Microsoft Academic database."""

    # Command to run on every paper
    command: Option = default(None)

    # Display long form for each paper
    long: Option & bool = default(False)

    papers = search()

    sch = search_commands

    for paper in papers:
        instruction = sch.process_paper(
            paper,
            command=command,
            formatter=Paper.format_term_long if long else Paper.format_term,
        )
        if instruction is False:
            break
