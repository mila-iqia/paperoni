from dataclasses import dataclass

from serieux import deserialize
from serieux.formats import FileSource

from ..model.classes import Paper
from ..model.focus import Focuses
from .base import Discoverer


@dataclass
class File(Discoverer):
    """Load papers from a file (JSON/YAML) containing a list of papers."""

    # Path to the file
    # [positional]
    path: FileSource

    # Key prefix for the generated papers
    key: str = None

    async def query(
        self,
        # Maximum number of papers to return (None = no limit)
        limit: int = None,
        # Number of papers to skip from the start
        offset: int = 0,
        # Focuses are not used here
        focuses: Focuses = None,
    ):
        """Yield papers from the file."""
        papers = deserialize(list[Paper], self.path)
        start = offset
        end = (offset + limit) if limit is not None else len(papers)
        for paper in papers[start:end]:
            paper.key = f"{self.key or self.path.path.stem}:{paper.id}"
            paper.info.setdefault("discovered_by", {})["staging"] = paper.id
            paper.id = None
            yield paper
