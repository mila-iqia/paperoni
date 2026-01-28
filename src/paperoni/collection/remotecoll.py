import os
from dataclasses import dataclass, field
from datetime import date
from typing import AsyncGenerator, Iterable

from fastapi import HTTPException
from serieux import deserialize
from serieux.features.encrypt import Secret

from ..get import Fetcher, RequestsFetcher
from ..model.classes import Paper
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

    async def exclusions(self) -> set[str]:
        raise NotImplementedError()

    async def add_exclusions(self, exclusions: list[str]) -> None:
        """Add exclusion strings."""
        raise NotImplementedError()

    async def remove_exclusions(self, exclusions: list[str]) -> None:
        """Remove exclusion strings."""
        raise NotImplementedError()

    async def is_excluded(self, s: str):
        """Return whether a link is excluded."""
        raise NotImplementedError()

    async def add_papers(self, papers: Iterable[Paper]) -> int:
        raise NotImplementedError()

    async def exclude_papers(self, papers: Iterable[Paper]) -> None:
        raise NotImplementedError()

    async def find_paper(self, paper: Paper) -> Paper | None:
        raise NotImplementedError()

    async def find_by_id(self, paper_id: int) -> Paper | None:
        url = f"{self.endpoint}/paper/{paper_id}"
        try:
            resp = await self.fetch.read(
                url,
                format="json",
                cache_into=None,
                headers=self.headers,
            )
            return deserialize(Paper, resp)
        except HTTPException as e:
            if e.status_code == 404:
                return None
            raise

    async def drop(self) -> None:
        raise NotImplementedError()

    async def search(
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
    ) -> AsyncGenerator[Paper, None]:
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
            params.setdefault("flags", []).extend(include_flags)
        if exclude_flags:
            params.setdefault("flags", []).extend([f"~{f}" for f in exclude_flags])
        url = f"{self.endpoint}/search"
        offset = 0
        while True:
            query_params = params.copy()
            query_params["offset"] = offset
            resp: dict = await self.fetch.read(
                url,
                format="json",
                cache_into=None,
                headers=self.headers,
                params=query_params,
            )
            papers = resp.get("results", [])
            for paper in papers:
                yield deserialize(Paper, paper)
            next_offset = resp.get("next_offset")
            if next_offset is None or not papers:
                break
            offset = next_offset

    def __len__(self) -> int:
        raise NotImplementedError()
