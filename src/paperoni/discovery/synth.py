from dataclasses import dataclass
from typing import Annotated, Any

from serieux import Auto
from serieux.features.tagset import FromEntryPoint

from ..model.focus import Focuses
from ..utils import soft_fail
from .base import Discoverer

DiscoT = Annotated[
    Any,
    FromEntryPoint(
        "paperoni.discovery",
        wrap=lambda cls: Auto[cls.query] if cls.__module__ != __name__ else None,
    ),
]


@dataclass
class Synth(Discoverer):
    """Query multiple discoverers."""

    # Dictionary of discoverers
    discoverers: dict[str, DiscoT]

    async def query(self, focuses: Focuses = None):
        """Query multiple discoverers."""
        for name, disco in self.discoverers.items():
            with soft_fail(f"discovery: {name}"):
                async for paper in disco(focuses=focuses):
                    yield paper
