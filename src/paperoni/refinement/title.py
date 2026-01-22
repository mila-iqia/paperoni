from types import SimpleNamespace
from typing import Literal
from urllib.parse import quote

from ..config import config
from ..discovery.openalex import OpenAlexQueryManager
from ..get import ERRORS
from .fetch import register_fetch
from .formats import paper_from_crossref, papers_from_arxiv


@register_fetch
async def crossref_title(typ: Literal["title"], link: str):
    """Fetch from Crossref by title search."""

    title = link

    # URL encode the title for the query
    encoded_title = quote(title.strip())

    try:
        data = await config.fetch.read(
            f"https://api.crossref.org/works?query.title={encoded_title}&rows=1",
            format="json",
        )
    except ERRORS as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    if data["status"] != "ok":  # pragma: no cover
        raise Exception("Request failed", data)

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    work_data = SimpleNamespace(**items[0])
    paper = await paper_from_crossref(work_data)
    if paper is None or paper.title != title:
        return None
    return paper


@register_fetch
async def openalex_title(typ: Literal["title"], link: str):
    """Fetch from OpenAlex by title search."""

    title = link

    qm = OpenAlexQueryManager(mailto=config.mailto)

    async for paper in qm.works(
        filter=f"display_name.search:{title.strip().replace(',', '')}",
        data_version="2",
        limit=1,
    ):
        paper = paper.paper
        if paper.title == title:
            return paper


@register_fetch
async def arxiv_title(type: Literal["title"], link: str):
    """Fetch from ArXiv by title search."""

    title = link

    try:
        soup = await config.fetch.read(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f'title:"{title}"',
                "start": "0",
                "max_results": "5",
            },
            format="xml",
        )
    except ERRORS as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise

    for paper in papers_from_arxiv(soup):
        if paper.title == title:
            return paper
