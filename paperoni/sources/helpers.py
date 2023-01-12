from collections import Counter

import questionary as qn
from coleo import Option, tooled
from giving import give

from ..display import display
from ..model import Link, UniqueAuthor


def prompt_controller(author, paper):
    display(paper)
    print("=" * 80)
    action = qn.text(
        f"Is this a paper by {author.name}? [y]es/[n]o/[m]ore/[s]kip/[d]one/[q]uit",
        validate=lambda x: x in ["y", "n", "m", "s", "d", "q"],
    ).unsafe_ask()
    return action


def _getname(x):
    return x.name


def filter_researchers(
    researchers, names=None, before=None, after=None, getname=_getname
):
    if names is not None:
        names = [n.lower() for n in names]
        researchers = [r for r in researchers if getname(r).lower() in names]

    researchers.sort(key=getname)

    if before is not None:
        researchers = [
            r
            for r in researchers
            if getname(r)[: len(before)].lower() < before.lower()
        ]

    if after is not None:
        researchers = [
            r
            for r in researchers
            if getname(r)[: len(after)].lower() > after.lower()
        ]

    return researchers


@tooled
def filter_researchers_interface(researchers, getname=_getname):
    # Only process researchers that come before this prefix
    before: Option = None

    # Only process researchers that come after this prefix
    after: Option = None

    # [action: append]
    names: Option = []

    return filter_researchers(
        researchers,
        names=names or None,
        before=before,
        after=after,
        getname=getname,
    )


def _fill_rids(rids, researchers, idtype):
    for researcher in researchers:
        for link in researcher.links:
            if link.type == idtype:
                rids[link.link] = researcher.name


def prepare(
    researchers,
    idtype,
    query_name,
    controller=prompt_controller,
    minimum=None,
):
    rids = {}
    _fill_rids(rids, researchers, idtype)

    def _ids(x, typ):
        return [link.link for link in x.links if link.type == typ]

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
            if not papers:  # pragma: no cover
                continue

            done = False

            (new_id,) = _ids(author, idtype)
            if new_id in ids or new_id in noids:
                give(author=aname, skip_id=new_id)
                continue

            aliases = {*author.aliases, author.name} - {aname}

            def _make(negate=False):
                auth = UniqueAuthor(
                    author_id=auq.author_id,
                    name=aname,
                    affiliations=[],
                    roles=[],
                    aliases=[] if negate else aliases,
                    links=[Link(type=f"!{idtype}", link=new_id)]
                    if negate
                    else author.links,
                )
                if not negate:
                    _fill_rids(rids, [auth], idtype)
                return auth

            papers = [
                (p.releases[0].venue.date.year, i, p)
                for i, p in enumerate(papers)
            ]
            papers.sort(reverse=True)

            give(
                author=author,
                author_name=aname,
                id=new_id,
                npapers=len(papers),
                common=dict(sorted(common.items(), key=lambda x: -x[1])),
                aliases=aliases,
                start_year=papers[-1][0],
                end_year=papers[0][0],
            )

            for _, _, p in papers:
                action = controller(author=auq, paper=p)
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
                else:  # pragma: no cover
                    raise Exception(f"Unknown action: {action}")

            if done:
                break


@tooled
def prepare_interface(
    researchers,
    idtype,
    query_name,
    controller=prompt_controller,
    minimum=None,
):
    # ID to give to the researcher
    # [option: --id]
    given_id: Option = None

    researchers = filter_researchers_interface(researchers)

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

    else:
        yield from prepare(
            researchers=researchers,
            controller=controller,
            idtype=idtype,
            minimum=minimum,
            query_name=query_name,
        )
