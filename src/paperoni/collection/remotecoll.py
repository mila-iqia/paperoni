import os
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from fastapi import HTTPException
from serieux import deserialize
from serieux.features.encrypt import Secret

from ..get import Fetcher, RequestsFetcher
from ..model.classes import CollectionPaper, Paper
from .abc import PaperCollection


@dataclass(kw_only=True)
class RemoteCollection(PaperCollection):
    endpoint: str
    token: Secret[str] = os.getenv("PAPERONI_TOKEN")
    fetch: Fetcher = field(default_factory=RequestsFetcher)

    def __post_init__(self):
        self.headers = {
            "Accept": "application/json",
        }
        if self.token is not None:
            self.headers["Authorization"] = f"Bearer {self.token}"

    @property
    def exclusions(self) -> set[str]:
        raise NotImplementedError()

    def add_papers(self, papers: Iterable[CollectionPaper]) -> int:
        raise NotImplementedError()

    def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    def find_paper(self, paper: Paper) -> CollectionPaper | None:
        raise NotImplementedError()

    def find_by_id(self, paper_id: int) -> CollectionPaper | None:
        url = f"{self.endpoint}/paper/{paper_id}"
        try:
            resp = self.fetch.read(
                url,
                format="json",
                cache_into=None,
                headers=self.headers,
            )
            return deserialize(CollectionPaper, resp)
        except HTTPException as e:
            if e.status_code == 404:
                return None
            raise

    def edit_paper(self, paper: CollectionPaper) -> None:
        raise NotImplementedError()

    def commit(self) -> None:
        raise NotImplementedError()

    def drop(self) -> None:
        raise NotImplementedError()

    def search(
        self,
        # Paper ID
        paper_id: int = None,
        # Title of the paper
        title: str = None,
        # Institution of an author
        institution: str = None,
        # Author of the paper
        author: str = None,
        # Venue name (long or short)
        venue: str = None,
        # Start date to consider
        start_date: date = None,
        # End date to consider
        end_date: date = None,
        # Flags that must be True
        include_flags: list[str] = None,
        # Flags that must be False
        exclude_flags: list[str] = None,
    ):
        params = {}
        if paper_id:
            params["paper_id"] = paper_id
        if title:
            params["title"] = title
        if institution:
            params["institution"] = institution
        if author:
            params["author"] = author
        if venue:
            params["venue"] = venue
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if include_flags:
            params["include_flags"] = ",".join(include_flags)
        if exclude_flags:
            params["exclude_flags"] = ",".join(exclude_flags)
        url = f"{self.endpoint}/search"
        offset = 0
        while True:
            query_params = params.copy()
            query_params["offset"] = offset
            resp = self.fetch.read(
                url,
                format="json",
                cache_into=None,
                headers=self.headers,
                params=query_params,
            )
            papers = resp.get("results", [])
            for paper in papers:
                yield deserialize(CollectionPaper, paper)
            next_offset = resp.get("next_offset")
            if next_offset is None or not papers:
                break
            offset = next_offset

    def __len__(self) -> int:
        raise NotImplementedError()
