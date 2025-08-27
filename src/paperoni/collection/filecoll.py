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
        if papers:
            self._papers.extend(papers)
            dump(list[Paper], self._papers, dest=self.papers_file)

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    self._exclusions.add(f"{link.type}:{link.link}")
        dump(set[str], self._exclusions, dest=self.exclusions_file)

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
        for p in self._papers:
            if title and title not in p.title:
                continue
            if author and not any(author in a.display_name for a in p.authors):
                continue
            if institution and not any(
                institution in aff.name for a in p.authors for aff in a.affiliations
            ):
                continue
            yield p

    def exclusions(self) -> set[str]:
        return self._exclusions
