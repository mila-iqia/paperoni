from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from hashlib import md5
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..tools import tag_uuid


class VenueType(str, Enum):
    journal = "journal"
    conference = "conference"
    workshop = "workshop"
    symposium = "symposium"
    book = "book"
    review = "review"
    news = "news"
    study = "study"
    meta_analysis = "meta_analysis"
    editorial = "editorial"
    letters_and_comments = "letters_and_comments"
    case_report = "case_report"
    clinical_trial = "clinical_trial"
    unknown = "unknown"
    challenge = "challenge"
    forum = "forum"
    track = "track"
    tutorials = "tutorials"
    seminar = "seminar"


class InstitutionCategory(str, Enum):
    industry = "industry"
    academia = "academia"
    unknown = "unknown"


class DatePrecision(int, Enum):
    unknown = 0
    year = 1
    month = 2
    day = 3

    @staticmethod
    def assimilate_date(date):
        match date:
            case int() as year:
                return {
                    "date": f"{year}-01-01 00:00",
                    "date_precision": DatePrecision.year,
                }
            case str() if m := re.match("^(....)-(..)-(..).*", date):
                match m.groups():
                    case (year, month, day):
                        if day == "01":
                            if month == "01":
                                precision = DatePrecision.year
                            else:
                                # precision = DatePrecision.month
                                precision = DatePrecision.day
                        else:
                            precision = DatePrecision.day
                        return {
                            "date": f"{year}-{month}-{day} 00:00",
                            "date_precision": precision,
                        }
                    case _:
                        assert False
            case None:
                return {
                    "date": "2000-01-01 00:00",
                    "date_precision": DatePrecision.unknown,
                }
            case _:
                assert False

    @staticmethod
    def format(date, precision):
        match DatePrecision(precision):
            case DatePrecision.year | DatePrecision.unknown:
                return date.strftime("%Y")
            case DatePrecision.month:
                return date.strftime("%Y-%m")
            case DatePrecision.day:
                return date.strftime("%Y-%m-%d")
            case _:
                assert False

    def format2(self, date):
        match self:
            case DatePrecision.year | DatePrecision.unknown:
                return date.strftime("%Y")
            case DatePrecision.month:
                return date.strftime("%Y-%m")
            case DatePrecision.day:
                return date.strftime("%Y-%m-%d")
            case _:
                assert False


class Base(BaseModel):
    def tagged_json(self):
        return self.__config__.json_dumps(
            {"__type__": type(self).__name__, **self.dict()},
            default=self.__json_encoder__,
        )

    def hashid(self):
        hsh = md5(self.json().encode("utf8"))
        return tag_uuid(hsh.digest(), "transient")


class Paper(Base):
    title: str
    abstract: str
    citation_count: int
    authors: list[Author]
    releases: list[Release]
    topics: list[Topic]
    links: list[Link]
    scrapers: list[str]


class Author(Base):
    name: str
    affiliations: list[Institution]
    roles: list[Role]
    aliases: list[str]
    links: list[Link]


class UniqueAuthor(Author):
    author_id: UUID = Field(default_factory=uuid4)

    def hashid(self):
        return self.author_id.bytes


class Institution(Base):
    name: str
    category: InstitutionCategory
    aliases: list[str]


class Release(Base):
    venue: Venue
    date: datetime
    date_precision: DatePrecision
    volume: Optional[str]
    publisher: Optional[str]


class Venue(Base):
    type: VenueType
    name: str
    links: list[Link]


class Topic(Base):
    name: str


class Link(Base):
    type: str
    link: str


class Role(Base):
    institution: Institution
    role: str
    start_date: datetime
    end_date: datetime | None


class AuthorPaperQuery(Base):
    author: Author
    start_date: datetime
    end_date: datetime | None


for cls in list(globals().values()):
    if isinstance(cls, type) and issubclass(cls, BaseModel):
        cls.update_forward_refs()


def from_dict(data):
    cls = globals()[data["__type__"]]
    return cls(**data)
