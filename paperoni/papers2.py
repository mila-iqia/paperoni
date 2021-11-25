from dataclasses import dataclass
from typing import Sequence

from .utils import T, asciiify, download, join, normalize as _norm, print_field

URL_SCHEMES = {
    "html": {
        "SemanticScholar": "https://www.semanticscholar.org/paper/{ref}",
        "ArXiv": "https://arxiv.org/abs/{ref}",
        "DBLP": "https://dblp.org/rec/{ref}",
        "DOI": "https://doi.org/{ref}",
    },
    "pdf": {"ArXiv": "https://arxiv.org/pdf/{ref}",},
}


@dataclass
class Link:
    type: str
    ref: str

    @property
    def urls(self):
        results = {}
        for format, schemes in URL_SCHEMES.items():
            pattern = schemes.get(self.type, None)
            if pattern is not None:
                results[format] = pattern.format(ref=self.ref)
        return results


@dataclass
class Topic:
    name: str = None


@dataclass
class Author:
    links: Sequence[Link] = ()
    name: str = None
    affiliations: Sequence[str] = ()


@dataclass
class Venue:
    code: str = None
    longname: str = None
    type: str = None
    preprint: bool = None

    @property
    def name(self):
        return self.longname or self.code


@dataclass
class Release:
    venue: Venue = None
    date: int = None
    year: int = None
    volume: str = None


@dataclass
class Paper:
    links: Sequence[Link] = ()
    title: str = None
    abstract: str = None
    authors: Sequence[Author] = ()
    releases: Sequence[Release] = ()
    topics: Sequence[Topic] = ()
    citation_count: int = None

    def __hash__(self):
        return hash((self.title, self.abstract))

    @property
    def date(self):
        date = None
        for release in self.releases:
            if release.date is not None:
                date = release.date
            elif release.year is not None:
                date = release.year
        return date

    @property
    def venue(self):
        for release in self.releases:
            return release.venue
        else:
            return None

    def format_term(self):
        """Print the paper on the terminal."""
        print_field("Title", T.bold(self.title))
        print_field("Authors", ", ".join(auth.name for auth in self.authors))
        if self.date is not None:
            print_field("Date", self.date)
        if self.venue:
            print_field("Venue", self.venue.code)
        print_field("URL", self.links[0].ref)

    def format_term_long(self):
        """Print the paper in long form on the terminal.

        Long form includes abstract, affiliations, keywords, number of
        citations.
        """
        print_field("Title", self.title)
        print_field("Authors", "")
        for auth in self.authors:
            print(f" * {auth.name:30} {', '.join(auth.affiliations)}")
        print_field("Abstract", self.abstract)
        if self.date is not None:
            print_field("Date", self.date)
        if self.venue:
            print_field(self.venue.type or "Venue", self.venue.name)
        print_field("Topics", ", ".join(t.name for t in self.topics))
        print_field("Sources", "")
        for link in self.links:
            for fmt, url in link.urls.items():
                print(f"  {T.bold_green(fmt)} {url}")

        print_field("Citations", self.citation_count)

    def get_ref(self, link_type):
        for link in self.links:
            if link.type == link_type:
                return link.ref
        else:
            return None
