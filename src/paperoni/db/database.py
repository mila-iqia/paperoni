import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ovld import OvldBase
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from tqdm import tqdm

from ..model import Author, Institution, Paper, PaperInfo, Release, Topic, Venue
from . import schema as sch

logger = logging.getLogger("paperoni.database")
logger.setLevel(level=logging.INFO)


class Database(OvldBase):
    DATABASE_SCRIPT_FILE = os.path.join(os.path.dirname(__file__), "database.sql")

    def __init__(self, filename):
        self.engine = create_engine(f"sqlite:///{filename}")
        connection = sqlite3.connect(filename)
        cursor = connection.cursor()
        with open(self.DATABASE_SCRIPT_FILE) as script_file:
            cursor.executescript(script_file.read())
            connection.commit()
        self.session = None
        self.cache = {}
        self._ctxlevel = 0

    def __enter__(self):
        if not self._ctxlevel:
            self.session = Session(self.engine).__enter__()
        self._ctxlevel += 1
        return self

    def __exit__(self, *args):
        self._ctxlevel -= 1
        if not self._ctxlevel:
            try:
                self.session.commit()
            except:
                self.session.rollback()
                raise
            finally:
                self.session.__exit__(*args)
                self.session = None

    def acquire(self, x: Any):
        entry = self._acquire(x)
        entry = self.session.merge(entry)
        self.session.flush()
        return entry

    def _acquire(self, x: PaperInfo):
        """Acquire a PaperInfo object into the database"""
        pp: sch.Paper = self.acquire(x.paper)

        # Store paper info
        pi = sch.PaperInfo(
            paper_id=pp.paper_id,
            key=x.key,
            update_key=x.update_key,
            info=x.info,
            acquired=int(x.acquired.timestamp()),
            score=x.score,
        )
        pi = self.session.merge(pi)

        return pi

    def _acquire(self, paper: Paper):
        """Acquire a Paper object into the database"""
        # Create paper entry
        pp = sch.Paper(
            paper_id=None,  # Let SQLAlchemy auto-generate
            title=paper.title,
            abstract=paper.abstract,
        )
        pp = self.session.merge(pp)
        self.session.flush()

        # Add authors
        for i, paper_author in enumerate(paper.authors):
            author: sch.Author = self.acquire(paper_author.author)
            pa = sch.PaperAuthor(
                paper_id=pp.paper_id,
                author_id=author.author_id,
                author_position=i,
                display_name=paper_author.display_name,
            )
            self.session.merge(pa)

            # Add affiliations
            for affiliation in paper_author.affiliations:
                institution: sch.Institution = self.acquire(affiliation)
                pai = sch.PaperAuthorInstitution(
                    paper_id=pp.paper_id,
                    author_id=author.author_id,
                    institution_id=institution.institution_id,
                )
                self.session.merge(pai)

        # Add releases
        for release in paper.releases:
            release: sch.Release = self.acquire(release)
            stmt = (
                insert(sch.t_paper_release)
                .values(paper_id=pp.paper_id, release_id=release.release_id)
                .on_conflict_do_nothing()
            )
            self.session.execute(stmt)

        # Add topics
        for topic in paper.topics:
            topic: sch.Topic = self.acquire(topic)
            stmt = (
                insert(sch.t_paper_topic)
                .values(paper_id=pp.paper_id, topic_id=topic.topic_id)
                .on_conflict_do_nothing()
            )
            self.session.execute(stmt)

        # Add links
        for link in paper.links:
            lnk = sch.PaperLink(
                paper_id=pp.paper_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        # Add flags
        for flag in paper.flags:
            flg = sch.PaperFlag(
                paper_id=pp.paper_id,
                flag_name=flag.flag_name,
                flag=flag.flag,
            )
            self.session.merge(flg)

        return pp

    def _acquire(self, author: Author):
        """Acquire an Author object into the database"""
        aa = sch.Author(
            author_id=None,  # Let SQLAlchemy auto-generate
            name=author.name,
        )
        aa = self.session.merge(aa)
        self.session.flush()

        # Add links
        for link in author.links:
            lnk = sch.AuthorLink(
                author_id=aa.author_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        # Add aliases
        for alias in set(author.aliases) | {author.name}:
            aal = sch.AuthorAlias(
                author_id=aa.author_id,
                alias=alias,
            )
            self.session.merge(aal)

        return aa

    def _acquire(self, institution: Institution):
        """Acquire an Institution object into the database"""
        inst = sch.Institution(
            institution_id=None,  # Let SQLAlchemy auto-generate
            name=institution.name,
            category=institution.category,
        )
        inst = self.session.merge(inst)
        self.session.flush()

        # Add aliases
        for alias in set(institution.aliases) | {institution.name}:
            ial = sch.InstitutionAlias(
                institution_id=inst.institution_id,
                alias=alias,
            )
            self.session.merge(ial)

        return inst

    def _acquire(self, release: Release):
        """Acquire a Release object into the database"""
        venue: sch.Venue = self.acquire(release.venue)

        rr = sch.Release(
            release_id=None,  # Let SQLAlchemy auto-generate
            venue_id=venue.venue_id,
            status=release.status,
            pages=release.pages,
        )
        rr = self.session.merge(rr)

        return rr

    def _acquire(self, topic: Topic):
        """Acquire a Topic object into the database"""
        tt = sch.Topic(
            topic_id=None,  # Let SQLAlchemy auto-generate
            name=topic.name,
        )
        tt = self.session.merge(tt)

        return tt

    def _acquire(self, venue: Venue):
        """Acquire a Venue object into the database"""
        vv = sch.Venue(
            venue_id=None,  # Let SQLAlchemy auto-generate
            type=venue.type.value,
            name=venue.name,
            series=venue.series,
            date=int(datetime.combine(venue.date, datetime.min.time()).timestamp()),
            date_precision=venue.date_precision.value,
            volume=venue.volume,
            publisher=venue.publisher,
        )
        vv = self.session.merge(vv)
        self.session.flush()

        # Add aliases
        for alias in set(venue.aliases) | {venue.name}:
            val = sch.VenueAlias(
                venue_id=vv.venue_id,
                alias=alias,
            )
            self.session.merge(val)

        # Add links
        for link in venue.links:
            lnk = sch.VenueLink(
                venue_id=vv.venue_id,
                type=link.type,
                link=link.link,
            )
            self.session.merge(lnk)

        return vv
