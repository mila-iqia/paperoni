from coleo import Option, tooled

from ...model import (
    Author,
    DatePrecision,
    Institution,
    InstitutionCategory,
    Link,
    Paper,
    PaperAuthor,
    Release,
    Venue,
    VenueType,
)
from ...utils import canonicalize_links
from ..acquire import HTTPSAcquirer
from .base import BaseScraper


class ZetaAlphaScraper(BaseScraper):
    def __init__(self, config, db):
        super().__init__(config=config, db=db)
        self.conn = HTTPSAcquirer(
            "api.zeta-alpha.com",
            delay=5 * 60 / 100,  # 100 requests per 5 minutes
            format="json",
        )

    def _evaluate(self, path: str, **params):
        return self.conn.get(
            f"/v0/service/documents/chunk/{path}", params=params
        )

    def _list(
        self,
        path: str,
        block_size: int = 100,
        limit: int = 10000,
        **params,
    ):
        params = {
            "page_size": min(block_size or 10000, limit),
            **params,
        }
        seen = 0
        while seen < limit:
            results = self._evaluate(path, **params)
            params["page"] = results["page"]
            hits = results["hits"]
            seen += len(hits)
            for entry in hits:
                yield entry
            if not results.get("next", None):
                break

    def _json_to_paper(self, entry):
        def _parse_release(m):
            date = DatePrecision.assimilate_date(m["created"])
            return Release(
                venue=Venue(
                    name=m["source"],
                    series=m["source"],
                    **date,
                    links=[],
                    aliases=[],
                    type=VenueType.unknown,
                ),
                pages=None,
                status="published",
            )

        def _parse_author(auth):
            return PaperAuthor(
                author=Author(
                    name=auth["full_name"],
                    links=[
                        Link(
                            type="zeta-alpha",
                            link=auth["uid"],
                        )
                    ],
                    roles=[],
                    aliases=[],
                    quality=(0.0,),
                ),
                affiliations=[
                    Institution(
                        name=aff,
                        category=InstitutionCategory.unknown,
                        aliases=[],
                    )
                    for aff in auth.get("affiliations", [])
                ],
            )

        m = entry["metadata"]
        entries = [entry, *entry["duplicates"]]

        return Paper(
            title=m["title"],
            abstract=m["abstract"],
            authors=[_parse_author(author) for author in m["creator"]],
            releases=[_parse_release(entry2["metadata"]) for entry2 in entries],
            links=[
                Link(**lnk)
                for lnk in canonicalize_links(
                    {"type": "html", "link": entry2["uri"]}
                    for entry2 in entries
                )
            ],
            topics=[],
            quality=(0.5,),
            citation_count=None,
        )

    @tooled
    def query(
        self,
        # Title of the paper
        # [alias: -t]
        # [nargs: +]
        title: Option = [],
        # Institution to search for
        # [alias: -i]
        # [nargs: +]
        institution: Option = [],
        # Maximal number of results per query
        block_size: Option & int = 100,
        # Maximal number of results to return
        limit: Option & int = 10000,
    ):
        results = self._list(
            path="search",
            query_string=" ".join(title),
            organizations=institution or None,
            # token=os.environ["ZETA_ALPHA_TOKEN"],
            # token=config.get().get_token("zeta_alpha")
            limit=limit,
            block_size=block_size,
        )
        for entry in results:
            yield self._json_to_paper(entry)

    @tooled
    def acquire(self):
        ...

    @tooled
    def prepare(self):
        pass


__scrapers__ = {
    "zeta-alpha": ZetaAlphaScraper,
}
