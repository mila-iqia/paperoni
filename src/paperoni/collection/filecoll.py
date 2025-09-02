import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterable

from serieux import deserialize, serialize

from ..model.classes import Paper
from .abc import PaperCollection

_id_types = {
    "arxiv",
    "dblp",
    "doi",
    "mlr",
    "openalex",
    "openreview",
    "pmc",
    "pubmed",
    "semantic_scholar",
    "uid",
}


@dataclass
class FileCollection(PaperCollection):
    directory: Path

    def __post_init__(self):
        if not self.directory.exists():
            self.directory.mkdir(exist_ok=True, parents=True)
        self.papers_file = self.directory / "papers.json"
        self.exclusions_file = self.directory / "exclusions.json"
        if not self.papers_file.exists():
            self.papers_file.write_text("[]")
        self._papers = deserialize(list[Paper], self.papers_file)
        if not self.exclusions_file.exists():
            self.exclusions_file.write_text("[]")
        self._exclusions = deserialize(set[str], self.exclusions_file)

    @cached_property
    def _by_title(self):
        return {p.title: p for p in self._papers}

    @cached_property
    def _by_link(self):
        return {link: p for p in self._papers for link in p.links}

    def add_papers(self, papers: Iterable[Paper]) -> None:
        papers = list(papers)
        if papers:
            self._papers.extend(papers)
            json.dump(
                fp=open(self.papers_file, "w"),
                obj=serialize(list[Paper], self._papers),
            )
            for p in papers:
                self._by_title[p.title.lower()] = p
                for link in p.links:
                    self._by_link[link] = p

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    self._exclusions.add(f"{link.type}:{link.link}")
        json.dump(
            fp=open(self.exclusions_file, "w"),
            obj=serialize(set[str], self._exclusions),
        )

    def find_paper(self, paper: Paper) -> Paper | None:
        for lnk in paper.links:
            if result := self._by_link.get(lnk, None):
                return result
        return self._by_title.get(paper.title, None)

    def search(
        self,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
    ):
        title = title and title.lower()
        author = author and author.lower()
        institution = institution and institution.lower()
        for p in self._papers:
            if title and title not in p.title.lower():
                continue
            if author and not any(author in a.display_name.lower() for a in p.authors):
                continue
            if institution and not any(
                institution in aff.name.lower()
                for a in p.authors
                for aff in a.affiliations
            ):
                continue
            yield p

    def exclusions(self) -> set[str]:
        return self._exclusions
