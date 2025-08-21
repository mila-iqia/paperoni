import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterable

from serieux import deserialize, serialize

from ..model.classes import Paper
from .tmpcoll import TmpCollection

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
class FileCollection(TmpCollection):
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
        super().add_papers(papers)
        if papers:
            json.dump(
                fp=open(self.papers_file, "w"),
                obj=serialize(list[Paper], self._papers),
            )

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        papers = list(papers)
        super().exclude_papers(papers)
        if papers:
            json.dump(
                fp=open(self.exclusions_file, "w"),
                obj=serialize(set[str], self._exclusions),
            )
