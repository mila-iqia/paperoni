import json
import re
from copy import deepcopy

from coleo import Argument as Arg, default, tooled

from ..config import get_config
from ..io import ResearchersFile
from ..papers import Papers
from ..query import QueryManager
from ..utils import T


def _add_role(researcher):
    status = None
    while not status:
        status = input(T.bold("Status: "))
    begin = input(T.bold("Begin (yyyy-mm-dd): ")).strip()
    end = input(T.bold("End (yyyy-mm-dd): ")).strip()
    begin = begin or None
    end = end or None
    for s in status.split(","):
        s = s.strip()
        researcher.data["roles"].append(
            {"status": s, "begin": begin, "end": end}
        )


@tooled
def _find_ids(rsch):

    # Microsoft Cognitive API key
    key: Arg & str = default(get_config("key"))

    # Query to use to find ids
    # [Alias: -q]
    query: Arg & str = default(rsch.data["name"])

    qm = QueryManager(key)
    queries = qm.interpret(query=f"{query}", count=10)

    # These will be modified in-place
    ids = rsch.data["ids"]
    noids = rsch.data["noids"]

    exit = False
    for q in queries:
        print("->", q)
        m = re.search(r"Composite\(AA\.AuN=='([^']*)'\)", q)
        if not m:
            continue
        auth_name = m.groups()[0]
        papers = qm.evaluate(
            q, ",".join(Papers.fields), orderby="D:desc", count=1000
        )
        papers = Papers({p["Id"]: p for p in papers}, None)
        for p in papers:
            aid = [
                auth.aid for auth in p.authors if auth.data["AuN"] == auth_name
            ]
            if not aid:
                continue
            aid = aid[0]
            if aid in noids or aid in ids:
                continue
            print("=" * 80)
            p.format_term()
            print("=" * 80)
            exit = False
            while True:
                answer = input(
                    f"Is this a paper by the author? (authid={aid}) [y]es/[n]o/[s]kip/[l]ong/[q]uit "
                )
                if answer == "y":
                    ids.append(aid)
                    break
                elif answer == "n":
                    noids.append(aid)
                    break
                elif answer == "s":
                    break
                elif answer == "l":
                    p.format_term_long()
                    print("=" * 80)
                elif answer == "q":
                    exit = True
                    break
            if exit:
                break
        if exit:
            break


@tooled
def command_researcher():
    """Register ids/statuses for a researcher."""

    # Researchers file (JSON)
    # [alias: -f -r]
    researchers: Arg & ResearchersFile

    # Name of the researcher
    # [alias: -a]
    # [nargs: +]
    author: Arg & str
    author = " ".join(author)

    data = researchers.get(author)

    original = deepcopy(data.data)

    while True:
        print(T.bold("Current data about"), T.bold_cyan(author))
        print(json.dumps(data.data, indent=2))
        print()

        print(T.bold("What do you want to do?"))
        print(T.bold_yellow("(1)"), "Find ids")
        print(T.bold_yellow("(2)"), "Add a role")
        print(T.bold_yellow("(*)"), "Quit (any other key)")
        task = input(T.bold("> "))

        if task == "1":
            print()
            _find_ids(data)

        elif task == "2":
            print()
            _add_role(data)

        else:
            break

    if data.data != original:
        save = input(T.bold("Save changes? [y]/n ")).strip()
        if save == "y" or save == "":
            researchers.save()
