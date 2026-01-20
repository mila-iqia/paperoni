"""Embedding service for semantic search using Google GenAI."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from google import genai
from google.genai.types import EmbedContentResponse
from paperazzi.utils import _make_key as paperazzi_make_key, disk_cache, disk_store
from serieux.features.encrypt import Secret


@dataclass
class EmbedContentResponseSerializer:
    @staticmethod
    def dump(response: EmbedContentResponse, file_obj: BinaryIO):
        model_dump = response.model_dump()
        return file_obj.write(
            json.dumps(model_dump, indent=2, ensure_ascii=False).encode("utf-8")
        )

    @staticmethod
    def load(file_obj: BinaryIO) -> EmbedContentResponse:
        data = json.load(file_obj)
        return EmbedContentResponse.model_validate(data)


@dataclass
class Embedding:
    """Service for generating and caching embeddings using Google GenAI."""

    client: genai.Client = None
    api_key: Secret[str] = None
    model: str = None

    def __post_init__(self):
        if self.client is None:
            self.client = genai.Client(api_key=self.api_key or None)

    def embed(
        self, contents: list[str], cache_dir: Path = None, **kwargs
    ) -> list[EmbedContentResponse]:
        """Embed content."""
        if cache_dir is not None:
            embed = self._embed.update(cache_dir=cache_dir)
        else:
            embed = self._embed

        return list(
            map(
                lambda c: embed(self.client, model=self.model, content=c, **kwargs),
                contents,
            )
        )

    @staticmethod
    def _make_key(_: tuple, kwargs: dict) -> str:
        kwargs = kwargs.copy()
        kwargs.pop("client", None)

        return paperazzi_make_key(None, kwargs)

    @disk_store
    @disk_cache(
        cache_dir=Path("/tmp/embeddings"),
        serializer=EmbedContentResponseSerializer,
        make_key=_make_key,
    )
    @staticmethod
    def _embed(
        client: genai.Client, *, model: str, content: str, **kwargs
    ) -> EmbedContentResponse:
        """Get embedding for text."""
        return client.models.embed_content(model=model, contents=[content], **kwargs)
