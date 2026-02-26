import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from functools import partial
from typing import Literal

from serieux import JSON

from ..utils import release_status_order

fromisoformat = date.fromisoformat

dataclass = partial(dataclass, kw_only=True)


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
    preprint = "preprint"
    dataset = "dataset"


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
    def assimilate_date(date, infer_precision=True):
        match date:
            case int() as year:
                if year < 100:
                    year += 2000
                return {
                    "date": datetime(year, 1, 1).date(),
                    "date_precision": DatePrecision.year,
                }
            case str() as year if re.match("^[0-9]{4}$", date):
                return {
                    "date": datetime(int(year), 1, 1).date(),
                    "date_precision": DatePrecision.year,
                }
            case str() if m := re.match("^(....)-(..)(-..)?.*", date):
                match m.groups():
                    case (year, month, day):
                        day = day and day[1:] or "01"
                        if infer_precision and day == "01":
                            if month == "01":
                                precision = DatePrecision.year
                            else:
                                precision = DatePrecision.month
                        else:
                            precision = DatePrecision.day
                        return {
                            "date": datetime(int(year), int(month), int(day)).date(),
                            "date_precision": precision,
                        }
                    case _:  # pragma: no cover
                        assert False
            case None | "":
                return (
                    {
                        "date": datetime(2000, 1, 1).date(),
                        "date_precision": DatePrecision.unknown,
                    }
                    if infer_precision
                    else None
                )
            case _:  # pragma: no cover
                assert False

    @staticmethod
    def make_date(date, alignment="start", infer_precision=False):
        date = DatePrecision.assimilate_date(date, infer_precision=infer_precision)
        if date is None:
            return None
        precision = date["date_precision"]
        assert precision != DatePrecision.month
        date = fromisoformat(date["date"][:10])
        if alignment == "start":
            return datetime(date.year, date.month, date.day)
        elif precision == DatePrecision.year:
            return datetime(date.year + 1, date.month, date.day) - timedelta(days=1)
        elif precision == DatePrecision.month:  # pragma: no cover
            return datetime(date.year, date.month + 1, date.day) - timedelta(days=1)
        else:
            return datetime(date.year, date.month, date.day)

    @staticmethod
    def format(date, precision):
        if isinstance(date, (int, float)):
            date = datetime.fromtimestamp(date)
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        match DatePrecision(precision):
            case DatePrecision.year | DatePrecision.unknown:
                return date.strftime("%Y")
            case DatePrecision.month:
                return date.strftime("%Y-%m")
            case DatePrecision.day:
                return date.strftime("%Y-%m-%d")
            case _:  # pragma: no cover
                assert False

    @staticmethod
    def pin(date, precision):
        if isinstance(date, (int, float)):
            date = datetime.fromtimestamp(date)
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        match DatePrecision(precision):
            case DatePrecision.year | DatePrecision.unknown:
                return datetime(year=date.year, month=1, day=1)
            case DatePrecision.month:
                return datetime(year=date.year, month=date.month, day=1)
            case DatePrecision.day:
                return datetime(year=date.year, month=date.month, day=date.day)
            case _:  # pragma: no cover
                assert False


class Base:
    class SerieuxConfig:
        allow_extras = True


@dataclass(frozen=True)
class Link:
    type: str
    link: str


@dataclass
class Topic:
    name: str


@dataclass
class Author(Base):
    name: str
    aliases: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


@dataclass
class Institution(Base):
    name: str
    category: InstitutionCategory = InstitutionCategory.unknown
    country: str = None
    aliases: list[str] = field(default_factory=list)

    def __hash__(self):
        return hash((self.name, self.category, self.country, tuple(self.aliases)))


@dataclass
class Venue:
    type: VenueType
    name: str
    series: str
    date: date
    date_precision: DatePrecision
    volume: str = None
    publisher: str = None
    short_name: str = None
    aliases: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    open: bool = False
    peer_reviewed: bool = False


@dataclass
class Release:
    venue: Venue
    status: str
    pages: str = None
    peer_review_status: Literal[
        "peer-reviewed",
        "preprint",
        "workshop",
        "other",
        "unknown",
    ] = "unknown"

    def __post_init__(self):
        if self.peer_review_status == "unknown":
            match release_status_order(self):
                case -1:
                    self.peer_review_status = "preprint"
                case 0:
                    self.peer_review_status = "workshop"
                case n if n > 0:
                    self.peer_review_status = "peer-reviewed"
                case _:
                    self.peer_review_status = "other"


@dataclass
class PaperAuthor(Base):
    author: Author
    display_name: str
    affiliations: list[Institution] = field(default_factory=list)


@dataclass
class Paper(Base):
    title: str
    abstract: str = None
    authors: list[PaperAuthor] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    # Info fields
    key: str = "n/a"
    info: dict[str, JSON] = field(default_factory=dict)
    score: float = 0.0

    # Collection fields
    id: int | str = None
    version: datetime = None

    def __post_init__(self):
        # For compatibility with existing databases
        # To delete later
        if isinstance(self.id, int):
            self.id = str(self.id)
