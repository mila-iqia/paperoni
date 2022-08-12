import datetime
import json
import os
import sqlite3
from pathlib import Path
from uuid import UUID

from ovld import OvldBase
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from tqdm import tqdm

from ..config import config
from ..model import (
    Author,
    AuthorMerge,
    Base,
    Institution,
    Meta,
    Paper,
    PaperMerge,
    Release,
    Topic,
    Venue,
    from_dict,
)
from ..tools import get_uuid_tag, is_canonical_uuid, squash_text, tag_uuid
from . import schema as sch


class Database(OvldBase):
    DATABASE_SCRIPT_FILE = os.path.join(
        os.path.dirname(__file__), "database.sql"
    )

    def __init__(self, filename):
        self.engine = create_engine(f"sqlite:///{filename}")
        connection = sqlite3.connect(filename)
        cursor = connection.cursor()
        with open(self.DATABASE_SCRIPT_FILE) as script_file:
            cursor.executescript(script_file.read())
            connection.commit()
        self.meta = None
        self.session = None
        self.cache = {}
        with self:
            self.canonical = {
                entry.hashid: entry.canonical
                for entry, in self.session.execute(select(sch.CanonicalId))
            }

    def __enter__(self):
        self.session = Session(self.engine).__enter__()
        return self

    def __exit__(self, *args):
        self.session.commit()
        self.session.__exit__(*args)
        self.session = None

    def acquire(self, m: Meta):
        self.meta = m

    def acquire(self, x: Base):
        # The id can be "transient" or "canonical". If it is "transient" it is defined
        # by its content, so we only ever need to acquire it once. If it is "canonical"
        # then it may contain new information we need to acquire, so we do not use the
        # cache for that.
        hid = x.hashid()
        tag = get_uuid_tag(hid)
        if hid in self.canonical:
            assert tag == "transient"
            return self.canonical[hid] or hid
        if not hid or tag == "canonical" or hid not in self.cache:
            self.cache[hid] = self._acquire(x)
            if tag == "transient":
                hid_object = sch.CanonicalId(hashid=hid, canonical=None)
                self.session.add(hid_object)
                if self.meta:
                    scr = sch.Scraper(
                        hashid=hid,
                        scraper=self.meta.scraper,
                        date=int(self.meta.date.timestamp()),
                    )
                    self.session.merge(scr)
        return self.cache[hid]

    def _acquire(self, paper: Paper):
        pp = sch.Paper(
            paper_id=paper.hashid(),
            title=paper.title,
            squashed=squash_text(paper.title),
            abstract=paper.abstract,
            citation_count=paper.citation_count,
        )
        self.session.merge(pp)

        for i, paper_author in enumerate(paper.authors):
            author = paper_author.author
            author_id = self.acquire(author)
            pa = sch.PaperAuthor(
                paper_id=pp.paper_id,
                author_id=author_id,
                author_position=i,
            )
            self.session.merge(pa)

            for affiliation in paper_author.affiliations:
                institution_id = self.acquire(affiliation)
                pai = sch.PaperAuthorInstitution(
                    paper_id=pp.paper_id,
                    author_id=author_id,
                    institution_id=institution_id,
                )
                self.session.merge(pai)

        for release in paper.releases:
            release_id = self.acquire(release)
            stmt = (
                insert(sch.t_paper_release)
                .values(paper_id=pp.paper_id, release_id=release_id)
                .on_conflict_do_nothing()
            )
            self.session.execute(stmt)

        for topic in paper.topics:
            topic_id = self.acquire(topic)
            stmt = (
                insert(sch.t_paper_topic)
                .values(paper_id=pp.paper_id, topic_id=topic_id)
                .on_conflict_do_nothing()
            )
            self.session.execute(stmt)

        for link in paper.links:
            lnk = sch.PaperLink(
                paper_id=pp.paper_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        return pp.paper_id

    def _acquire(self, author: Author):
        aa = sch.Author(author_id=author.hashid(), name=author.name)
        self.session.merge(aa)

        for link in author.links:
            lnk = sch.AuthorLink(
                author_id=aa.author_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        for alias in set(author.aliases) | {author.name}:
            aal = sch.AuthorAlias(
                author_id=aa.author_id,
                alias=alias,
            )
            self.session.merge(aal)

        for role in author.roles:
            rr = sch.AuthorInstitution(
                author_id=aa.author_id,
                institution_id=self.acquire(role.institution),
                role=role.role,
                start_date=role.start_date,
                end_date=role.end_date,
            )
            self.session.merge(rr)

        return aa.author_id

    def _acquire(self, institution: Institution):
        inst = sch.Institution(
            institution_id=institution.hashid(),
            name=institution.name,
            category=institution.category,
        )
        self.session.merge(inst)
        return inst.institution_id

    def _acquire(self, release: Release):
        venue_id = self.acquire(release.venue)
        rr = sch.Release(
            release_id=release.hashid(),
            venue_id=venue_id,
            status=release.status,
            pages=release.pages,
        )
        self.session.merge(rr)
        return rr.release_id

    def _acquire(self, topic: Topic):
        tt = sch.Topic(topic_id=topic.hashid(), topic=topic.name)
        self.session.merge(tt)
        return tt.topic_id

    def _acquire(self, venue: Venue):
        vv = sch.Venue(
            venue_id=venue.hashid(),
            type=venue.type,
            name=venue.name,
            date=venue.date.timestamp(),
            date_precision=venue.date_precision,
            volume=venue.volume,
            publisher=venue.publisher,
        )
        self.session.merge(vv)

        for link in venue.links:
            lnk = sch.VenueLink(
                venue_id=vv.venue_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        return vv.venue_id

    def _acquire(self, merge: AuthorMerge):
        self._merge_ids_for_table(
            table=sch.Author,
            id_field="author_id",
            ids=merge.ids,
            redirects={
                sch.PaperAuthor: "author_id",
                sch.PaperAuthorInstitution: "author_id",
                sch.AuthorLink: "author_id",
                sch.AuthorAlias: "author_id",
                sch.AuthorInstitution: "author_id",
                sch.Scraper: "hashid",
            },
        )

    def _acquire(self, merge: PaperMerge):
        self._merge_ids_for_table(
            table=sch.Paper,
            id_field="paper_id",
            ids=merge.ids,
            redirects={
                sch.PaperAuthor: "paper_id",
                sch.PaperLink: "paper_id",
                sch.PaperFlag: "paper_id",
                sch.PaperAuthorInstitution: "paper_id",
                sch.t_paper_release: "paper_id",
                sch.t_paper_topic: "paper_id",
                sch.Scraper: "hashid",
            },
        )

    def import_all(self, xs: list[BaseModel], history_file=None):
        if not xs:
            return
        history_file = history_file or config.history_file
        xs = list(xs)
        with self:
            for x in tqdm(xs):
                self.acquire(x)
        with open(history_file, "a") as f:
            data = [x.tagged_json() + "\n" for x in xs]
            f.writelines(data)

    def _accumulate_history_files(self, x, before, after, results):
        match x:
            case str() as pth:
                return self._accumulate_history_files(
                    Path(pth), before, after, results
                )
            case Path() as pth:
                if pth.is_dir():
                    self._accumulate_history_files(
                        list(pth.iterdir()), before, after, results
                    )
                else:
                    results.append(pth)
            case [*paths]:
                paths = list(sorted(paths))
                if before:
                    paths = [x for x in paths if x.name[: len(before)] < before]
                if after:
                    paths = [x for x in paths if x.name[: len(after)] > after]
                for subpth in paths:
                    self._accumulate_history_files(
                        subpth, before, after, results
                    )
            case _:
                assert False

    def replay(self, history=None, before=None, after=None):
        history = history or config.history_root
        history_files = []
        self._accumulate_history_files(history, before, after, history_files)
        for history_file in history_files:
            print(f"Replaying {history_file}")
            with self:
                with open(history_file, "r") as f:
                    lines = f.readlines()
                    for l in tqdm(lines):
                        self.acquire(from_dict(json.loads(l)))

    def _filter_ids(self, ids, create_canonical):
        for x in ids:
            if is_canonical_uuid(x.bytes):
                canonical = x
                break
        else:
            ids.sort(key=lambda i: i.hex)
            canonical = UUID(bytes=tag_uuid(ids[0].bytes, "canonical"))
            create_canonical(canonical, x)
        return canonical, [x for x in ids if x != canonical]

    def _merge_ids_for_table(
        self,
        table,
        redirects,
        id_field,
        ids,
    ):
        def conds(field=id_field):
            conds = [f"{field} = X'{pid.hex}'" for pid in ids]
            return " OR ".join(conds)

        table = getattr(table, "__table__", table)
        fields = [column.name for column in table.columns]

        def create_canonical(canonical, model):
            values = [
                f"X'{canonical.hex}'" if f == id_field else f for f in fields
            ]
            stmt = f"""
            INSERT OR IGNORE INTO {table.name} ({", ".join(fields)})
            SELECT {", ".join(values)} FROM {table.name} WHERE {id_field} = X'{model.hex}'
            """
            self.session.execute(stmt)

        canonical, ids = self._filter_ids(ids, create_canonical)

        for subtable, field in redirects.items():
            subtable = getattr(subtable, "__table__", subtable)
            stmt = f"""
            UPDATE OR REPLACE {subtable}
            SET {field} = X'{canonical.hex}'
            WHERE {conds(field)}
            """
            self.session.execute(stmt)

        stmt = f"""
        DELETE FROM {table.name} WHERE {conds()}
        """
        self.session.execute(stmt)
