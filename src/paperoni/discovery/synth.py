from dataclasses import dataclass
from typing import Annotated, Any

from serieux import Auto
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
    def serieux_deserialize(cls, obj, ctx, call_next):
        return cls(call_next(list[DiscoT], obj, ctx))

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return call_next(list[DiscoT], obj.discoverers, ctx)


@dataclass
class Synth(Discoverer):
    """Query multiple discoverers."""

    # List of discoverers
    discoverers: DiscoBag

    def query(self, focuses: Focuses):
        for disco in self.discoverers.discoverers:
            yield from disco(focuses=focuses)
