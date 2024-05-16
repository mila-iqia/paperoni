import time
from datetime import datetime, timedelta

from coleo import Option, tooled
from sqlalchemy import select

from paperoni.sources.acquire import readpage
from paperoni.utils import asciiify

from ... import model as M
from ...db import schema as sch


class BaseScraper:
    def __init__(self, config, db):
        self.config = config
        self.db = db

    @tooled
    def generate_ids(
        self,
        scraper,
        extend_back: Option & int = 30 * 12,
        cutoff: Option & int = 30 * 12 * 15,
    ):
        if cutoff and isinstance(cutoff, int):
            cutoff = datetime.now() - timedelta(days=cutoff)
        q = """
        SELECT author.name,
               group_concat(scrape_id,";;;;;"),
               min(author_institution.start_date),
               max(IFNULL(author_institution.end_date, 10000000000))
            FROM author_scrape_ids
            JOIN author ON author.author_id = author_scrape_ids.author_id
            JOIN author_institution ON author.author_id = author_institution.author_id
        WHERE scraper = :scraper AND active = 1
        GROUP BY author.author_id
        """
        results = self.db.session.execute(q, {"scraper": scraper})
        for name, ids, start, end in results:
            ids = set(ids.split(";;;;;"))
            start -= timedelta(days=extend_back).total_seconds()
            start = max(cutoff, datetime.fromtimestamp(start))
            end = end and datetime.fromtimestamp(end)
            if start < end:
                yield name, ids, start, end

    @tooled
    def generate_paper_queries(self, cutoff: Option & int = -30 * 6):
        if cutoff and isinstance(cutoff, int):
            cutoff = datetime.now() - timedelta(days=-cutoff)
        with self.db:
            q = select(sch.AuthorInstitution)
            queries = []
            for ai in self.db.session.execute(q):
                (ai,) = ai
                if ai.role == "chair":
                    continue
                if (
                    cutoff
                    and ai.end_date
                    and datetime.fromtimestamp(ai.end_date) < cutoff
                ):
                    continue
                paper_query = M.AuthorPaperQuery(
                    author=M.UniqueAuthor(
                        author_id=ai.author_id,
                        name=ai.author.name,
                        affiliations=[],
                        roles=[],
                        aliases=ai.author.aliases,
                        links=[
                            M.Link(
                                type=link.type,
                                link=link.link,
                            )
                            for link in ai.author.links
                        ],
                    ),
                    start_date=ai.start_date,
                    end_date=ai.end_date,
                )
                queries.append(paper_query)

            return queries

    def generate_author_queries(self):
        authors = {}
        for pq in self.generate_paper_queries():
            authors[pq.author.author_id] = pq.author
        return [author for author in authors.values()]


class ProceedingsScraper(BaseScraper):
    @tooled
    def query(
        self,
        # Volume(s) to query
        # [alias: -v]
        # [action: append]
        volume: Option = None,
        # Name(s) to query
        # [alias: --name]
        # [action: append]
        name: Option = None,
        # Whether to cache the download
        # [negate]
        cache: Option & bool = True,
    ):
        names = name and {asciiify(n).lower() for n in name}
        for i, vol in enumerate(volume):
            if i > 0:
                time.sleep(1)
            results = self.get_volume(vol, names, cache)
            for paper in results:
                if not paper:
                    continue
                if names is None or any(
                    asciiify(auth.author.name).lower() in names
                    for auth in paper.authors
                ):
                    yield paper

    def extract_volumes(self, index, selector, map=None, filter=None):
        main = readpage(index, format="html")
        urls = [lnk.attrs["href"] for lnk in main.select(selector)]
        return [
            map(url) if map else url
            for url in urls
            if filter is None or filter(url)
        ]

    def list_names(self, institution="Mila"):
        q = """
        SELECT DISTINCT alias from author
               JOIN author_alias as aa ON author.author_id = aa.author_id
               JOIN author_institution as ai ON ai.author_id = author.author_id
               JOIN institution as it ON it.institution_id = ai.institution_id
            WHERE it.name = :institution;
        """
        return [
            name
            for (name,) in self.db.session.execute(
                q, {"institution": institution}
            )
        ]

    @tooled
    def acquire(self):
        volumes = self.list_volumes()
        names = self.list_names()
        yield M.Meta(
            scraper=self.scraper_name,
            date=datetime.now(),
        )
        yield from self.query(
            volume=volumes,
            name=names,
        )

    @tooled
    def prepare(self):
        pass
