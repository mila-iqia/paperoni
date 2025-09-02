from typing import Iterable

from ..model.classes import Paper


class PaperCollection:
    def add_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> Paper | None:
        raise NotImplementedError()

    def exclusions(self) -> set[str]:
        raise NotImplementedError()
