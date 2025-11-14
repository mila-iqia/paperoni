from dataclasses import dataclass
from typing import Annotated, Any

from serieux import Auto, Field, Model
from serieux.features.tagset import FromEntryPoint

from ..model.focus import Focuses
from .base import Discoverer

DiscoT = Annotated[
    Any,
    FromEntryPoint(
        "paperoni.discovery",
        wrap=lambda cls: Auto[cls.query] if cls.__module__ != __name__ else None,
    ),
]


@dataclass
class DiscoBag:
    discoverers: list[DiscoT]

    @classmethod
    def serieux_model(cls, call_next):
        return Model(
            original_type=cls,
            element_field=Field(name="_", type=DiscoT),
            from_list=cls,
        )


@dataclass
class Synth(Discoverer):
    """Query multiple discoverers."""

    # List of discoverers
    discoverers: DiscoBag

    def query(self, focuses: Focuses):
        """Query multiple discoverers."""
        for disco in self.discoverers.discoverers:
            yield from disco(focuses=focuses)
