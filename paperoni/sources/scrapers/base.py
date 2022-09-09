from sqlalchemy import select

from ... import model as M
from ...db import schema as sch


class BaseScraper:
    def __init__(self, config, db):
        self.config = config
        self.db = db

    def generate_paper_queries(self):
        q = select(sch.AuthorInstitution)
        queries = []
        for ai in self.db.session.execute(q):
            (ai,) = ai
            paper_query = M.AuthorPaperQuery(
                author=M.Author(
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
        q = select(sch.AuthorInstitution)
        authors = {}
        for ai in self.db.session.execute(q):
            (ai,) = ai
            authors[ai.author.author_id] = M.UniqueAuthor(
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
            )

        results = [author for author in authors.values()]
        return results
