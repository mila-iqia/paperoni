from dataclasses import dataclass, field
from pathlib import Path

import gifnoc

from ...model import Topic, VenueType
from ...model.classes import Base
from ...prompt import PromptConfig
from ...prompt_utils import Explained


@dataclass
class Venue:
    type: VenueType
    name: str
    series: str
    date: str
    volume: str = ""
    publisher: str = ""


@dataclass
class Release:
    venue: Venue
    pages: str = ""


@dataclass
class PaperAuthor(Base):
    display_name: str


@dataclass
class Paper(Base):
    title: str
    authors: list[PaperAuthor] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)


@dataclass
class Analysis:
    # The parsed paper object
    paper: Explained[Paper]


DEFAULT_SYSTEM_MESSAGE = (Path(__file__).parent / "system-prompt.md").read_text()
FIRST_MESSAGE = """### Paper citation to analyze:

{}"""

llm_config: PromptConfig = gifnoc.define(
    "paperoni.llm_citation",
    PromptConfig,
    defaults={"system_prompt_template": DEFAULT_SYSTEM_MESSAGE},
)
