from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional


class VenueType(str, Enum):
    journal = "journal"
    conference = "conference"
    workshop = "workshop"
    symposium = "symposium"
    unknown = "unknown"


class Paper(BaseModel):
    title: str
    abstract: str
    citation_count: int
    authors: list[Author]
    releases: list[Release]
    topics: list[Topic]
    links: list[Link]


class Author(BaseModel):
    name: str
    affiliations: list[Affiliation]
    links: list[Link]


class Affiliation(BaseModel):
    name: str


class Release(BaseModel):
    venue: Venue
    date: datetime
    date_precision: int
    volume: Optional[str]
    publisher: Optional[str]


class Venue(BaseModel):
    type: VenueType
    name: str
    links: list[Link]


class Topic(BaseModel):
    name: str


class Link(BaseModel):
    type: str
    link: str


for cls in list(globals().values()):
    if isinstance(cls, type) and issubclass(cls, BaseModel):
        cls.update_forward_refs()


def from_dict(data):
    cls = globals()[data["__type__"]]
    return cls(**data)
