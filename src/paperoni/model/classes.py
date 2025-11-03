import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from functools import partial
from typing import Callable

from serieux import JSON

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
                    "date": datetime(year, 1, 1).date(),
                    "date_precision": DatePrecision.year,
                }
            case str() if m := re.match("^(....)-(..)-(..).*", date):
                match m.groups():
                    case (year, month, day):
                        if infer_precision and day == "01":
                            if month == "01":
                                precision = DatePrecision.year
                            else:
                                precision = DatePrecision.day
                        else:
                            precision = DatePrecision.day
                        return {
                            "date": datetime(year, month, day).date(),
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


@dataclass(frozen=True)
class Link:
    type: str
    link: str


@dataclass
class Flag:
    flag_name: str
    flag: bool


@dataclass
class Topic:
    name: str


@dataclass
class Author:
    name: str
    aliases: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


@dataclass
class Institution:
    name: str
    category: InstitutionCategory = InstitutionCategory.unknown
    aliases: list[str] = field(default_factory=list)


@dataclass
class Venue:
    type: VenueType
    name: str
    series: str
    date: date
    date_precision: DatePrecision
    volume: str = None
    publisher: str = None
    aliases: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    open: bool = False
    peer_reviewed: bool = False


@dataclass
class Release:
    venue: Venue
    status: str
    pages: str = None


@dataclass
class PaperAuthor:
    author: Author
    display_name: str
    affiliations: list[Institution] = field(default_factory=list)


@dataclass
class Paper:
    title: str
    abstract: str = None
    authors: list[PaperAuthor] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


@dataclass
class PaperInfo:
    paper: Paper
    key: str
    info: dict[str, JSON] = field(default_factory=dict)
    acquired: datetime = field(default_factory=datetime.now)
    score: float = 0.0


def rescore(stream, score):
    for pinfo in stream:
        pinfo.score = score
        yield pinfo


@dataclass
class CollectionMixin:
    id: int = None
    version: datetime = None

    @classmethod
    def make_collection_item(
        cls,
        item,
        *,
        next_id: Callable[[], int] = lambda: None,
        **defaults,
    ) -> "CollectionMixin":
        # Avoid errors coming from extra fields like '_id'
        kwargs = {k: v for k, v in vars(item).items() if k in cls.__dataclass_fields__}
        item = cls(**{**defaults, **kwargs})
        item.id = next_id() if item.id is None else item.id
        item.version = datetime.now() if item.version is None else item.version
        return item


@dataclass
class CollectionPaper(Paper, CollectionMixin):
    pass
