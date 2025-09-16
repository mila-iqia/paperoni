from typing import Iterable

from ..model.classes import CollectionPaper, Paper


class PaperCollection:
    @property
    def exclusions(self) -> set[str]:
        raise NotImplementedError()

    def add_papers(self, papers: Iterable[CollectionPaper]) -> None:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> CollectionPaper | None:
        raise NotImplementedError()

    def commit(self) -> None:
        raise NotImplementedError()
