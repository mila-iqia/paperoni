import gifnoc
from serieux import TaggedSubclass

from .discovery.base import Discoverer

discoverers = gifnoc.define(
    "paperoni.discovery",
    dict[str, TaggedSubclass[Discoverer]],
)
