from collections import Counter

import questionary as qn
from coleo import Option, tooled

from ..model import Link, UniqueAuthor
from ..utils import display


@tooled
def prepare(
    researchers,
    idtype,
    query_name,
    minimum=None,
):
    after: Option = ""
    name: Option = ""

    # ID to give to the researcher
    # [option: --id]
    given_id: Option = None

    rids = {}
    for researcher in researchers:
        for link in researcher.links:
            if link.type == idtype:
                rids[link.link] = researcher.name

    def _ids(x, typ):
        return [link.link for link in x.links if link.type == typ]

    researchers.sort(key=lambda auq: auq.name.lower())
    if name:
        researchers = [
            auq for auq in researchers if auq.name.lower() == name.lower()
        ]
    elif after:
        researchers = [
            auq for auq in researchers if auq.name.lower()[: len(after)] > after
        ]

    if given_id:
        assert len(researchers) == 1
        for auq in researchers:
            yield UniqueAuthor(
                author_id=auq.author_id,
                name=auq.name,
                affiliations=[],
                roles=[],
                aliases=[],
                links=[Link(type=idtype, link=given_id)],
            )
        return

    for auq in researchers:
        aname = auq.name
        ids = set(_ids(auq, idtype))
        noids = set(_ids(auq, f"!{idtype}"))

        def find_common(papers):
            common = Counter()
            for p in papers:
                for a in p.authors:
                    for l in a.author.links:
                        if l.type == idtype and l.link in rids:
                            common[rids[l.link]] += 1
            return sum(common.values()), common

        data = [
            (author, *find_common(papers), papers)
            for author, papers in query_name(aname)
            if not minimum or len(papers) > minimum
        ]
        data.sort(key=lambda ap: (-ap[1], -len(ap[-1])))

        for author, _, common, papers in data:
            if not papers:
                continue

            done = False

            (new_id,) = _ids(author, idtype)
            if new_id in ids or new_id in noids:
                print(f"Skipping processed ID for {aname}: {new_id}")
                continue
            aliases = {*author.aliases, author.name} - {aname}

            def _make(negate=False):
                return UniqueAuthor(
                    author_id=auq.author_id,
                    name=aname,
                    affiliations=[],
                    roles=[],
                    aliases=[] if negate else aliases,
                    links=[Link(type=f"!{idtype}", link=new_id)]
                    if negate
                    else author.links,
                )

            print("=" * 80)
            print(f"{aname} (ID = {new_id}): {len(papers)} paper(s)")
            for name, count in sorted(common.items(), key=lambda x: -x[1]):
                print(f"{count} with {name}")

            print(f"Aliases: {aliases}")
            papers = [
                (p.releases[0].venue.date.year, i, p)
                for i, p in enumerate(papers)
            ]
            papers.sort(reverse=True)
            print(f"Years: {papers[-1][0]} to {papers[0][0]}")
            print("=" * 80)
            for _, _, p in papers:
                display(p)
                print("=" * 80)
                action = qn.text(
                    f"Is this a paper by {aname}? [y]es/[n]o/[m]ore/[s]kip/[d]one/[q]uit",
                    validate=lambda x: x in ["y", "n", "m", "s", "d", "q"],
                ).unsafe_ask()
                if action == "y":
                    yield _make()
                    break
                elif action == "n":
                    yield _make(negate=True)
                    break
                elif action == "d":
                    done = True
                    break
                elif action == "m":
                    continue
                elif action == "s":
                    break
                elif action == "q":
                    return

            if done:
                break
