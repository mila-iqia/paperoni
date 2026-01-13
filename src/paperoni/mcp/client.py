"""HTTP client for paperoni REST API."""

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import HTTPException
from serieux.features.encrypt import Secret

from ..get import Fetcher, RequestsFetcher


@dataclass
class PaperoniAPIClient:
    """Client for interacting with paperoni REST API."""

    endpoint: str
    token: Secret[str] = os.getenv("PAPERONI_TOKEN")
    fetch: Fetcher = field(default_factory=RequestsFetcher)

    def __post_init__(self):
        self.headers = {
            "Accept": "application/json",
        }
        if self.token is not None:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def search_papers(
        self,
        paper_id: int = None,
        title: str = None,
        institution: str = None,
        author: str = None,
        venue: str = None,
        start_date: date = None,
        end_date: date = None,
        include_flags: list[str] = None,
        exclude_flags: list[str] = None,
        query: str = None,
        similarity_threshold: float = 0.75,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
        }

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
        if query:
            params["query"] = query
        if similarity_threshold:
            params["similarity_threshold"] = similarity_threshold

        url = f"{self.endpoint}/api/v1/search"

        try:
            resp = self.fetch.read(
                url,
                format="json",
                cache_into=None,
                headers=self.headers,
                params=params,
            )
            resp.pop("total", None)
            return resp

        except Exception as e:
            if isinstance(e, HTTPException) and e.status_code == 404:
                return {
                    "results": [],
                    "similarities": None,
                    "count": 0,
                    "next_offset": None,
                }
            raise

    def count_papers(
        self,
        paper_id: int = None,
        title: str = None,
        institution: str = None,
        author: str = None,
        venue: str = None,
        start_date: date = None,
        end_date: date = None,
        include_flags: list[str] = None,
        exclude_flags: list[str] = None,
    ) -> int:
        # Fetch first page to get total count
        resp = self.search_papers(
            paper_id=paper_id,
            title=title,
            institution=institution,
            author=author,
            venue=venue,
            start_date=start_date,
            end_date=end_date,
            include_flags=include_flags,
            exclude_flags=exclude_flags,
            offset=0,
            limit=1,  # Only need the total count
        )
        return resp.get("total", 0)
