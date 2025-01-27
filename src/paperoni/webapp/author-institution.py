import json
from datetime import datetime
from hashlib import md5
from pathlib import Path

import yaml
from sqlalchemy import select

from ..config import papconf
from ..db import schema as sch
from ..model import (
    Institution,
    Role,
    ScraperID,
    UniqueAuthor,
    UniqueInstitution,
)
from ..utils import tag_uuid
from .common import (
    ContentEditor,
    mila_template,
)

here = Path(__file__).parent


class DBPatch:
    def get(self):
        pass

    def reset(self):
        pass

    def put(self, data):
        pass


class ResearchersPatch(DBPatch):
    def __init__(self, institution):
        with papconf.database as db:
            stmt = select(sch.Institution)
            stmt = stmt.where(sch.Institution.name == institution.name)
            stmt = stmt.limit(1)
            results = list(db.session.execute(stmt))
            if results:
                ((existing,),) = results
                self.institution = UniqueInstitution(
                    institution_id=existing.institution_id,
                    name=existing.name,
                    category=existing.category,
                    aliases=existing.aliases,
                )
            else:
                self.institution = Institution(
                    name=institution.name,
                    category=institution.category,
                    aliases=institution.aliases,
                )

    def generate(self, db, filter=None):
        stmt = select(sch.Author)
        stmt = stmt.join(sch.AuthorInstitution)
        stmt = stmt.order_by(sch.Author.name)
        if filter is not None:
            stmt = stmt.where(sch.Author.name.like(f"%{filter}%"))
        stmt = stmt.distinct()
        for (result,) in db.session.execute(stmt):
            yield result

    def get(self, filter=None):
        with papconf.database as db:
            cfg = {}
            for row in self.generate(db, filter):
                cfg[row.name] = UniqueAuthor(
                    author_id=row.author_id.hex(),
                    name=row.name,
                    aliases=[],
                    links=[],
                    roles=[
                        Role(
                            role=role.role,
                            start_date=datetime.fromtimestamp(role.start_date),
                            end_date=role.end_date
                            and datetime.fromtimestamp(role.end_date),
                            institution=self.institution,
                        )
                        for role in row.roles
                        if role.institution.name == self.institution.name
                    ],
                    scraper_ids=[
                        ScraperID(
                            scrape_id=lnk.scrape_id,
                            scraper=lnk.scraper,
                            active=bool(lnk.active),
                        )
                        for lnk in row.scrape_ids
                    ],
                )
            return cfg

    def reset(self, filter=None):
        with papconf.database as db:
            for row in self.generate(db, filter):
                for sid in row.scrape_ids:
                    q = """
                        DELETE FROM author_scrape_ids
                        WHERE scraper = :scraper
                        AND scrape_id = :scrape_id
                    """
                    db.session.execute(
                        q,
                        params={
                            "scraper": sid.scraper,
                            "scrape_id": sid.scrape_id,
                        },
                    )
                for role in row.roles:
                    db.session.delete(role)

    def put(self, data):
        with papconf.database as db:
            for _, author in data.items():
                db.acquire(author)
        return True


class DBEditor(ContentEditor):
    def __init__(self, patch):
        self.patch = patch
        super().__init__(language="yaml", show_filter=True)

    def simplify(self, data):
        for v in data.values():
            for field in ["aliases", "links"]:
                if not v[field]:
                    del v[field]
            del v["quality"]
            for role in v["roles"]:
                del role["institution"]
        return data

    def repopulate(self, data):
        for v in data.values():
            v["quality"] = (0.0,)
            for role in v["roles"]:
                role["institution"] = self.patch.institution
        return data

    def read(self):
        data = self.patch.get(self.filter if self.filter else None)
        ser = {k: json.loads(v.json()) for k, v in data.items()}
        return yaml.safe_dump(self.simplify(ser))

    def wrap(self, new):
        def mk(v):
            if "author_id" not in v:
                v["author_id"] = tag_uuid(
                    md5(v["name"].encode("utf8")).digest(), "canonical"
                )
            return UniqueAuthor(**v)

        return {
            k: mk(v) for k, v in self.repopulate(yaml.safe_load(new)).items()
        }

    def change(self, new):
        self.wrap(new)
        return True

    def submit(self, new):
        data = self.wrap(new)
        self.patch.reset(self.filter if self.filter else None)
        return self.patch.put(data)


@mila_template(title="List of researchers", help="/help#author-institution")
async def __app__(page, box):
    """Edit/update the list of researchers."""
    inst = Institution(
        category="academia",
        name="Mila",
        aliases=[],
    )
    page.print(DBEditor(ResearchersPatch(inst)))
