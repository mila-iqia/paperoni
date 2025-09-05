import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterable

from serieux import deserialize, serialize

from ..model.classes import Paper
from .abc import CollectionPaper
from .tmpcoll import TmpCollection


@dataclass
class FileCollection(TmpCollection):
    directory: Path
    _next_paper_id: int = -1

    def __post_init__(self):
        if not self.directory.exists():
            self.directory.mkdir(exist_ok=True, parents=True)

        self._last_id_file = self.directory / "_last_id"
        self.papers_file = self.directory / "papers.json"
        self.exclusions_file = self.directory / "exclusions.json"

        if not self._last_id_file.exists():
            self._last_id_file.write_text("-1")
        self._next_paper_id = int(self._last_id_file.read_text())
        if not self.papers_file.exists():
            self.papers_file.write_text("[]")
        self._papers = deserialize(list[CollectionPaper], self.papers_file)
        if not self.exclusions_file.exists():
            self.exclusions_file.write_text("[]")
        self._exclusions = deserialize(set[str], self.exclusions_file)

    @cached_property
    def _by_title(self):
        return {p.title: p for p in self._papers}

    @cached_property
    def _by_link(self):
        return {link: p for p in self._papers for link in p.links}

    def next_paper_id(self) -> int:
        # In case we added papers without incrementing the id, reset the first
        # id to the length of the papers
        self._next_paper_id += 1
        self._last_id_file.write_text(str(self._next_paper_id))
        return self._next_paper_id

    def add_papers(self, papers: Iterable[Paper | CollectionPaper]) -> None:
        if super().add_papers(papers):
            json.dump(
                fp=open(self.papers_file, "w"),
                obj=serialize(list[CollectionPaper], self._papers),
            )

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        papers = list(papers)
        super().exclude_papers(papers)
        if papers:
            json.dump(
                fp=open(self.exclusions_file, "w"),
                obj=serialize(set[str], self._exclusions),
            )
