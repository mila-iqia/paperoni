from dataclasses import dataclass

from ..prompt_utils import Explained


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
