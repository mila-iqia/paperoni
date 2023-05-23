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
    MergeEntry,
    Meta,
    Paper,
    PaperMerge,
    Release,
    ScraperData,
    SimpleBase,
    Topic,
    Venue,
    VenueMerge,
    from_dict,
)
from ..utils import get_uuid_tag, is_canonical_uuid, squash_text, tag_uuid
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
        self._ctxlevel = 0
        with self:
            self.canonical = {
                entry.hashid: entry.canonical
                for entry, in self.session.execute(select(sch.CanonicalId))
            }

    def __enter__(self):
        if not self._ctxlevel:
            self.session = Session(self.engine).__enter__()
        self._ctxlevel += 1
        return self

    def __exit__(self, *args):
        self._ctxlevel -= 1
        if not self._ctxlevel:
            self.session.commit()
            self.session.__exit__(*args)
            self.session = None

    def acquire(self, m: Meta):
        self.meta = m

    def acquire(self, x: SimpleBase):
        entry = self._acquire(x)
        self.session.merge(entry)
        return entry

    def acquire(self, x: Base):
        # The id can be "transient" or "canonical". If it is "transient" it is defined
        # by its content, so we only ever need to acquire it once. If it is "canonical"
        # then it may contain new information we need to acquire, so we do not use the
        # cache for that.
        hid = x.hashid()
        tag = get_uuid_tag(hid)
        if hid in self.canonical and tag == "transient":
            return self.canonical[hid] or hid
        if not hid or tag == "canonical" or hid not in self.cache:
            self.cache[hid] = self._acquire(x)
            if tag == "transient":
                hid_object = sch.CanonicalId(hashid=hid, canonical=hid)
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
            quality=paper.quality_int(),
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
        aa = sch.Author(
            author_id=author.hashid(),
            name=author.name,
            quality=author.quality_int(),
        )

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
                start_date=role.start_date and role.start_date.timestamp(),
                end_date=role.end_date and role.end_date.timestamp(),
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

        for alias in set(institution.aliases) | {institution.name}:
            ial = sch.InstitutionAlias(
                institution_id=inst.institution_id,
                alias=alias,
            )
            self.session.merge(ial)

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
            quality=venue.quality_int(),
        )
        self.session.merge(vv)

        for alias in set(venue.aliases) | {venue.name}:
            val = sch.VenueAlias(
                venue_id=vv.venue_id,
                alias=alias,
            )
            self.session.merge(val)

        for link in venue.links:
            lnk = sch.VenueLink(
                venue_id=vv.venue_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        return vv.venue_id

    def _acquire(self, x: ScraperData):
        return sch.ScraperData(
            scraper=x.scraper,
            tag=x.tag,
            date=x.date,
            data=x.data,
        )

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
                sch.CanonicalId: "canonical",
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
                sch.CanonicalId: "canonical",
            },
        )

    def _acquire(self, merge: VenueMerge):
        self._merge_ids_for_table(
            table=sch.Venue,
            id_field="venue_id",
            ids=merge.ids,
            redirects={
                sch.Release: "venue_id",
                sch.VenueLink: "venue_id",
                sch.VenueAlias: "venue_id",
                sch.Scraper: "hashid",
                sch.CanonicalId: "canonical",
            },
        )

    def import_all(self, xs: list[BaseModel], history_file=True):
        if not xs:
            return
        if history_file is True:
            history_file = config.get().history_file
        xs = list(xs)
        with self:
            for x in tqdm(xs):
                self.acquire(x)
        if history_file:
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
                elif pth.suffix == ".jsonl":
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
        history = history or config.get().paths.history
        history_files = []
        self._accumulate_history_files(history, before, after, history_files)
        for history_file in history_files:
            print(f"Replaying {history_file}")
            with self:
                with open(history_file, "r") as f:
                    lines = f.readlines()
                    for l in tqdm(lines):
                        if l.strip():
                            self.acquire(from_dict(json.loads(l)))

    def _filter_ids(self, ids, create_canonical):
        for x in ids:
            if is_canonical_uuid(x.id.bytes):
                canonical = x
                break
        else:
            ids.sort(key=lambda i: i.id.hex)
            canonical = MergeEntry(
                id=UUID(bytes=tag_uuid(ids[0].id.bytes, "canonical")),
                quality=0,
            )
            create_canonical(canonical.id, x.id)
        return canonical, [x for x in ids if x != canonical]

    def _merge_ids_for_table(
        self,
        table,
        redirects,
        id_field,
        ids,
    ):
        ids = sorted(ids, key=lambda entry: entry.id.hex, reverse=True)

        def conds(field=id_field):
            conds = [f"{field} = X'{pid.id.hex}'" for pid in ids]
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
            SET {field} = X'{canonical.id.hex}'
            WHERE {conds(field)}
            """
            self.session.execute(stmt)

        # Merge existing entries, starting with the one with the best quality
        # This uses a bunch of coalesce() calls in sqlite which returns the first
        # non-null entry.

        nonid_fields = [field for field in fields if field != id_field]
        contributors = [canonical, *ids]
        contributors.sort(reverse=True, key=lambda m: m.quality)
        # We only keep the 10 best because coalesce() has a limit on the number of
        # arguments and it's unlikely that we will need to pull info past the top
        # ten (in the worst case we can tweak the quality metric to reflect the number
        # of non-null fields)
        contributors = contributors[:10]
        best, *rest = contributors

        joins = [
            f" JOIN {table.name} as t{i + 1} ON t{i + 1}.{id_field} = X'{m.id.hex}'"
            for i, m in enumerate(rest)
        ]
        coalesce_parts = [
            (field, [f"t{i}.{field}" for i in range(len(contributors))])
            for field in nonid_fields
        ]
        coalesces = [
            f"coalesce({','.join(parts)}) as value__{field}"
            for field, parts in coalesce_parts
        ]
        updates = [f"{field} = value__{field}" for field in nonid_fields]

        # Set up forwarding to the canonical ID

        canhex = f"X'{canonical.id.hex}'"
        canon_stmt = f"""
        UPDATE canonical_id
        SET canonical = {canhex}
        WHERE {conds('hashid')} OR {conds('canonical')}
        """
        self.session.execute(canon_stmt)

        canon_ins_stmt = f"""
        INSERT INTO canonical_id(hashid, canonical)
        VALUES ({canhex}, {canhex})
        ON CONFLICT(hashid) DO UPDATE
        SET canonical = {canhex}
        """
        self.session.execute(canon_ins_stmt)

        merge_stmt = f"""
        UPDATE {table.name}
        SET {", ".join(updates)}
        FROM (
            SELECT {', '.join(coalesces)}
            FROM {table.name} as t0
            {" ".join(joins)}
            WHERE t0.{id_field} = X'{best.id.hex}'
        )
        WHERE {id_field} = X'{canonical.id.hex}'
        """
        self.session.execute(merge_stmt)

        # Delete all the entries we merged except for the main one (canonical)

        del_stmt = f"""
        DELETE FROM {table.name} WHERE {conds()}
        """
        self.session.execute(del_stmt)

    def insert_flag(self, paper, flag_name, val):
        pf = sch.PaperFlag(
            paper_id=paper.paper_id,
        )
        ins_stmt = f"""
        INSERT INTO {pf.__tablename__}
        VALUES (X'{paper.paper_id.hex()}',"{flag_name}",{val})
        """

        self.session.execute(ins_stmt)
        self.session.commit()

    def remove_flags(self, paper, flag_name):
        pf = sch.PaperFlag(
            paper_id=paper.paper_id,
        )
        del_stmt = f"""
        DELETE FROM {pf.__tablename__}
        WHERE paper_id = X'{paper.paper_id.hex()}' AND flag_name = "{flag_name}"
        """
        self.session.execute(del_stmt)
        self.session.commit()

    def has_flag(self, paper, flagname):
        for flag in paper.paper_flag:
            if flag.flag_name == flagname:
                return True
        return False

    def insert_author(self, author_id, name, quality):
        ins_stmt = f"""
        INSERT INTO author
        VALUES (X'{author_id}',"{name}",{quality})
        """
        self.session.execute(ins_stmt)
        self.session.commit()

    def insert_author_institution(
        self, author_id, institution_id, role, start_date, end_date
    ):
        author = sch.AuthorInstitution(
            author_id=author_id,
        )
        ins_stmt = f"""
        INSERT INTO {author.__tablename__}
        VALUES (X'{author.author_id}',"{institution_id}",{role}, {start_date})
        """
        self.session.execute(ins_stmt)
        self.session.commit()

    def insert_author_link(self, author_id, type, link):
        author_link = sch.AuthorLink(
            author_id=author_id,
        )
        ins_stmt = f"""
        INSERT INTO {author_link.__tablename__}
        VALUES (X'{author_id.hex()}',"{type}","{link}")
        """
        self.session.execute(ins_stmt)
        self.session.commit()
    
    def update_author_link(self, author_id, type, old_link, new_link):
        author_link = sch.AuthorLink(
            author_id=author_id,
        )
        upd_stmt = f"""
        UPDATE {author_link.__tablename__}
        SET link = "{new_link}"
        WHERE link = "{old_link}" AND type = "{type}"
        """
        self.session.execute(upd_stmt)
        self.session.commit()