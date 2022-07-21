import json
import urllib.parse
from typing import Counter

import questionary as qn
from coleo import Option, tooled

from ...utils import QueryError, display
from ..acquire import HTTPSAcquirer
from ..model import (
    Author,
    AuthorQuery,
    DatePrecision,
    Link,
    Paper,
    Release,
    Topic,
    Venue,
    VenueType,
)

external_ids_mapping = {
    "pubmedcentral": "pmc",
}


venue_type_mapping = {
    "JournalArticle": VenueType.journal,
    "Conference": VenueType.conference,
    "Book": VenueType.book,
    "Review": VenueType.review,
    "News": VenueType.news,
    "Study": VenueType.study,
    "MetaAnalysis": VenueType.meta_analysis,
    "Editorial": VenueType.editorial,
    "LettersAndComments": VenueType.letters_and_comments,
    "CaseReport": VenueType.case_report,
    "ClinicalTrial": VenueType.clinical_trial,
    "_": VenueType.unknown,
}


def _paper_long_fields(parent=None, extras=()):
    fields = (
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "venue",
        "publicationTypes",
        "publicationDate",
        "year",
        "journal",
        "referenceCount",
        "citationCount",
        "influentialCitationCount",
        "isOpenAccess",
        "fieldsOfStudy",
        *extras,
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


def _paper_short_fields(parent=None):
    fields = (
        "paperId",
        "url",
        "title",
        "venue",
        "year",
        "authors",  # {authorId, name}
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


def _author_fields(parent=None):
    fields = (
        "authorId",
        "externalIds",
        "url",
        "name",
        "aliases",
        "affiliations",
        "homepage",
        "paperCount",
        "citationCount",
    )
    return (
        fields
        if parent is None
        else tuple(f"{parent}.{field}" for field in fields)
    )


class SemanticScholarQueryManager:
    # "authors" will have fields "authorId" and "name"
    SEARCH_FIELDS = _paper_long_fields(extras=("authors",))
    PAPER_FIELDS = (
        *_paper_long_fields(),
        *_author_fields(parent="authors"),
        *_paper_short_fields(parent="citations"),
        *_paper_short_fields(parent="references"),
        "embedding",
    )
    PAPER_AUTHORS_FIELDS = _author_fields() + _paper_long_fields(
        parent="papers", extras=("authors",)
    )
    PAPER_CITATIONS_FIELDS = (
        "contexts",
        "intents",
        "isInfluential",
        *SEARCH_FIELDS,
    )
    PAPER_REFERENCES_FIELDS = PAPER_CITATIONS_FIELDS
    AUTHOR_FIELDS = PAPER_AUTHORS_FIELDS
    AUTHOR_PAPERS_FIELDS = (
        SEARCH_FIELDS
        + _paper_short_fields(parent="citations")
        + _paper_short_fields(parent="references")
    )

    def __init__(self):
        self.conn = HTTPSAcquirer(
            "api.semanticscholar.org",
            delay=5 * 60 / 100,  # 100 requests per 5 minutes
        )

    def _evaluate(self, path: str, **params):
        params = urllib.parse.urlencode(params)
        data = self.conn.get(f"/graph/v1/{path}?{params}")
        jdata = json.loads(data)
        if "error" in jdata:
            raise QueryError(jdata["error"])
        return jdata

    def _list(
        self,
        path: str,
        fields: tuple[str],
        block_size: int = 100,
        limit: int = 10000,
        **params,
    ):
        params = {
            "fields": ",".join(fields),
            "limit": min(block_size or 10000, limit),
            **params,
        }
        next_offset = 0
        while next_offset is not None and next_offset < limit:
            results = self._evaluate(path, offset=next_offset, **params)
            next_offset = results.get("next", None)
            for entry in results["data"]:
                yield entry

    def _wrap_author(self, data):
        lnk = (aid := data["authorId"]) and Link(
            type="semantic_scholar", link=aid
        )
        return Author(
            name=data["name"],
            affiliations=[],
            aliases=data.get("aliases", None) or [],
            links=[lnk] if lnk else [],
            roles=[],
        )

    def _wrap_paper(self, data):
        links = [Link(type="semantic_scholar", link=data["paperId"])]
        for typ, ref in data["externalIds"].items():
            links.append(
                Link(
                    type=external_ids_mapping.get(t := typ.lower(), t), link=ref
                )
            )
        authors = list(map(self._wrap_author, data["authors"]))
        # date = data["publicationDate"] or f'{data["year"]}-01-01'
        if pubd := data["publicationDate"]:
            date = {
                "date": f"{pubd} 00:00",
                "date_precision": DatePrecision.day,
            }
        else:
            date = DatePrecision.assimilate_date(data["year"])
        release = Release(
            venue=Venue(
                type=venue_type_mapping[
                    (pubt := data.get("publicationTypes", []))
                    and pubt[0]
                    or "_"
                ],
                name=data["venue"],
                volume=(j := data["journal"]) and j.get("volume", None),
                links=[],
            ),
            **date,
        )
        return Paper(
            links=links,
            authors=authors,
            title=data["title"],
            abstract=data["abstract"] or "",
            citation_count=data["citationCount"],
            topics=[
                Topic(name=field) for field in (data["fieldsOfStudy"] or ())
            ],
            releases=[release],
            scrapers=["ssch"],
        )

    def search(self, query, fields=SEARCH_FIELDS, **params):
        papers = self._list(
            "paper/search",
            query=query,
            fields=fields,
            **params,
        )
        yield from map(self._wrap_paper, papers)

    def paper(self, paper_id, fields=PAPER_FIELDS):
        (paper,) = self._list(f"paper/{paper_id}", fields=fields)
        return paper

    def paper_authors(self, paper_id, fields=PAPER_AUTHORS_FIELDS, **params):
        yield from self._list(
            f"paper/{paper_id}/authors", fields=fields, **params
        )

    def paper_citations(
        self, paper_id, fields=PAPER_CITATIONS_FIELDS, **params
    ):
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def paper_references(
        self, paper_id, fields=PAPER_REFERENCES_FIELDS, **params
    ):
        yield from self._list(
            f"paper/{paper_id}/citations", fields=fields, **params
        )

    def author(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list(
            f"author/search", query=name, fields=fields, **params
        )
        yield from map(self._wrap_author, authors)

    def author_with_papers(self, name, fields=AUTHOR_FIELDS, **params):
        name = name.replace("-", " ")
        authors = self._list(
            f"author/search", query=name, fields=fields, **params
        )
        for author in authors:
            yield (
                self._wrap_author(author),
                [self._wrap_paper(p) for p in author["papers"]],
            )

    def author_papers(self, author_id, fields=AUTHOR_PAPERS_FIELDS, **params):
        papers = self._list(
            f"author/{author_id}/papers", fields=fields, **params
        )
        yield from map(self._wrap_paper, papers)


def _between(name, after, before):
    name = name.lower()
    if after and name[: len(after)] <= after:
        return False
    if before and name[: len(before)] >= before:
        return False
    return True


class SemanticScholarScraper:
    name = "semantic_scholar"

    @tooled
    def query(
        self,
        # Author to query
        # [alias: -a]
        # [nargs: +]
        author: Option = [],
        # Title of the paper
        # [alias: -t]
        # [nargs: +]
        title: Option = [],
        # Maximal number of results per query
        block_size: Option & int = 100,
        # Maximal number of results to return
        limit: Option & int = 10000,
    ):
        author = " ".join(author)
        title = " ".join(title)

        if author and title:
            raise QueryError("Cannot query both author and title")

        ss = SemanticScholarQueryManager()

        if title:
            yield from ss.search(title, block_size=block_size, limit=limit)

        elif author:
            for auth in ss.author(author):
                print(auth)

    @tooled
    def acquire(self, queries):
        todo = {}

        after: Option = ""
        before: Option = ""

        queries.sort(key=lambda auq: auq.author.name.lower())

        for auq in queries:
            if not _between(auq.author.name, after, before):
                continue
            for link in auq.author.links:
                if link.type == "semantic_scholar":
                    todo[link.link] = auq

        ss = SemanticScholarQueryManager()

        for ssid, auq in todo.items():
            print(f"Fetch papers for {auq.author.name} (ID={ssid})")
            yield from ss.author_papers(ssid, block_size=1000)

    @tooled
    def prepare(self, researchers):
        after: Option = ""
        name: Option = ""

        rids = {}
        for researcher in researchers:
            for link in researcher.author.links:
                if link.type == "semantic_scholar":
                    rids[link.link] = researcher.author.name

        ss = SemanticScholarQueryManager()

        def _ids(x, typ):
            return [link.link for link in x.links if link.type == typ]

        researchers.sort(key=lambda auq: auq.author.name.lower())
        if name:
            researchers = [
                auq for auq in researchers if auq.author.name.lower() == name
            ]
        elif after:
            researchers = [
                auq
                for auq in researchers
                if auq.author.name.lower()[: len(after)] > after
            ]

        for auq in researchers:
            aname = auq.author.name
            ids = set(_ids(auq.author, "semantic_scholar"))
            noids = set(_ids(auq.author, "!semantic_scholar"))

            def find_common(papers):
                common = Counter()
                for p in papers:
                    for a in p.authors:
                        for l in a.links:
                            if l.type == "semantic_scholar" and l.link in rids:
                                common[rids[l.link]] += 1
                return sum(common.values()), common

            data = [
                (author, *find_common(papers), papers)
                for author, papers in ss.author_with_papers(aname)
                if len(papers) > 1
            ]
            data.sort(key=lambda ap: (-ap[1], -len(ap[-1])))

            for author, _, common, papers in data:
                if not papers:
                    continue

                done = False

                (new_id,) = _ids(author)
                if new_id in ids or new_id in noids:
                    print(f"Skipping processed ID for {aname}: {new_id}")
                    continue
                aliases = {*author.aliases, author.name} - {aname}

                def _make(negate=False):
                    return AuthorQuery(
                        author_id=auq.author_id,
                        author=Author(
                            name=aname,
                            affiliations=[],
                            roles=[],
                            aliases=[] if negate else aliases,
                            links=[Link(type="!semantic_scholar", link=new_id)]
                            if negate
                            else author.links,
                        ),
                    )

                print("=" * 80)
                print(f"{aname} (ID = {new_id}): {len(papers)} paper(s)")
                for name, count in sorted(common.items(), key=lambda x: -x[1]):
                    print(f"{count} with {name}")

                print(f"Aliases: {aliases}")
                papers = [
                    (p.releases[0].date.year, i, p)
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


__scrapers__ = {"semantic_scholar": SemanticScholarScraper()}
