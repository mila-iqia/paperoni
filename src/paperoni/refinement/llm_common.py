from dataclasses import dataclass
from typing import Annotated

from serieux import Comment


@dataclass
class Explained:
    # A detailed explanation for the choice of the value
    reasoning: str
    # The best literal quote from the paper which supports the value
    quote: str

    def __class_getitem__(cls, t):
        return Annotated[t, Comment(cls, required=True)]


@dataclass
class AuthorAffiliations:
    # An author present in the Deep Learning scientific paper
    author: Explained[str]
    # List of the author's affiliations present in the Deep Learning scientific paper
    affiliations: list[Explained[str]]


@dataclass
class Analysis:
    # The title of the Deep Learning scientific paper
    title: Explained[str]

    # List of all authors present in the Deep Learning scientific paper with theirs affiliations
    authors_affiliations: list[AuthorAffiliations]
    # List of all affiliations present in the Deep Learning scientific paper
    affiliations: list[Explained[str]]
