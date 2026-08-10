from typing import Literal

from openreview import OpenReviewException

from ..config import config
from ..discovery.openalex import WORK_TYPES, OpenAlexQueryManager
from ..discovery.openreview import OpenReviewDispatch
from ..discovery.semantic_scholar import SemanticScholar
from ..get import ERRORS
from .fetch import register_fetch


@register_fetch(tags={"extra"})
async def semantic_scholar(typ: Literal["semantic_scholar"], link: str):
    """Fetch from Semantic Scholar by paper ID."""

    try:
        return await SemanticScholar().paper(link)
    except ERRORS as exc:  # pragma: no cover
        if exc.response.status_code == 404:
            return None
        else:
            raise


@register_fetch(tags={"extra"})
async def openalex(typ: Literal["openalex"], link: str):
    """Fetch from OpenAlex by work ID."""

    qm = OpenAlexQueryManager(mailto=config.mailto, work_types=WORK_TYPES)

    async for paper in qm.works(
        filter=f"ids.openalex:{link}",
        data_version="2",
        limit=1,
    ):
        return paper


@register_fetch(tags={"extra"})
async def openreview(typ: Literal["openreview"], link: str):
    """Fetch from OpenReview by paper ID, using the note's metadata."""

    try:
        async for paper in OpenReviewDispatch().query(paper_id=link, limit=1):
            return paper
    except OpenReviewException as exc:
        error = exc.args[0] if exc.args else None
        if isinstance(error, dict) and error.get("status") == 404:
            return None
        raise
