from datetime import date
from typing import Iterable

from ..model.classes import CollectionPaper, Paper


class PaperCollection:
    @property
    def exclusions(self) -> set[str]:
        raise NotImplementedError()

    def add_papers(self, papers: Iterable[CollectionPaper]) -> int:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> CollectionPaper | None:
        raise NotImplementedError()

    def commit(self) -> None:
        raise NotImplementedError()

    def search(
        self,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
        # Start date to consider
        start_date: date = None,
        # End date to consider
        end_date: date = None,
    ) -> Iterable[CollectionPaper]:
        raise NotImplementedError()
