"""MCP server implementation using fastmcp."""

from datetime import date

from fastmcp import FastMCP

from ..config import config
from .client import PaperoniAPIClient


def create_mcp(endpoint: str = None):
    api_client = PaperoniAPIClient(
        endpoint or config.mcp.api_client.endpoint,
        token=config.mcp.api_client.token,
        fetch=config.mcp.api_client.fetch,
    )

    mcp = FastMCP(name="Paperoni")

    @mcp.tool
    def search_papers(
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
    ):
        """Search for papers in the paperoni collection.

        This tool allows searching for papers using various filters including
        semantic search, institution, venue, author, and date ranges. Results
        include paper metadata (title, abstract, authors, venues, topics) but
        exclude PDF content.

        If a query is provided, the results will be sorted by similarity score.
        Note that unrelated papers may still be returned with a low similarity
        score.

        Args:
            paper_id: Paper ID
            title: Title of the paper
            institution: Institution of an author
            author: Author of the paper
            venue: Venue name (long or short)
            start_date: Start date to consider
            end_date: End date to consider
            include_flags: Flags that must be present
            exclude_flags: Flags that must not be present
            query: Semantic search query
            similarity_threshold: Similarity threshold (default: 0.75)
            offset: Pagination offset (default: 0)
            limit: Maximum number of results to return (default: 100)

        Returns:
            Dictionary containing:
            - results: List of paper objects with metadata
            - similarities: List of similarity scores (None if no query was provided)
            - count: Number of results in this page
            - next_offset: Offset for next page (None if no more pages)
        """

        return api_client.search_papers(
            paper_id=paper_id,
            title=title,
            institution=institution,
            author=author,
            venue=venue,
            start_date=start_date,
            end_date=end_date,
            include_flags=include_flags,
            exclude_flags=exclude_flags,
            query=query,
            similarity_threshold=similarity_threshold,
            offset=offset,
            limit=limit,
        )

    @mcp.tool
    def count_papers(
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
        """Count papers matching criteria without fetching all results.

        Args:
            paper_id: Paper ID
            title: Title of the paper
            institution: Institution of an author
            author: Author of the paper
            venue: Venue name (long or short)
            start_date: Start date to consider
            end_date: End date to consider
            include_flags: Flags that must be present
            exclude_flags: Flags that must not be present

        Returns:
            Total count of matching papers
        """

        return api_client.count_papers(
            paper_id=paper_id,
            title=title,
            institution=institution,
            author=author,
            venue=venue,
            start_date=start_date,
            end_date=end_date,
            include_flags=include_flags,
            exclude_flags=exclude_flags,
        )

    return mcp
