from typing import Iterable

import numpy as np
from google import genai
from google.genai.types import EmbedContentResponse

from ..config import config
from ..model.classes import Paper


class PaperEmbedding:
    @staticmethod
    def semantic_search(
        papers: Iterable[Paper], query: str, similarity_threshold: float = 0.75
    ) -> list[tuple[Paper, float]]:
        """Semantic search for papers."""
        responses: Iterable[EmbedContentResponse] = map(
            PaperEmbedding.get_paper_embedding, papers
        )
        store = np.array([r.embeddings[0].values for r in responses])
        query_embedding = np.array(
            config.embedding.embed(
                [query],
                cache_dir=None,
                config=genai.types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
            )[0]
            .embeddings[0]
            .values
        )

        # Calculate Cosine Similarity
        # Formula: (A dot B) / (||A|| * ||B||)
        dot_products = np.dot(store, query_embedding)
        norms = np.linalg.norm(store, axis=1) * np.linalg.norm(query_embedding)
        similarities = dot_products / norms

        # Return sorted results
        sorted_indices = np.argsort(similarities)[::-1]
        return [
            (papers[i], similarities[i])
            for i in sorted_indices
            if similarities[i] >= similarity_threshold
        ]

    @staticmethod
    def get_paper_embedding(paper: Paper) -> list[float] | None:
        """Get embedding for a paper (title + abstract + topics)."""
        parts = [paper.title]

        if paper.abstract:
            parts.append(paper.abstract)

        if paper.topics:
            topic_names = ", ".join(sorted(t.name.lower() for t in paper.topics))
            parts.append(f"Topics: {topic_names}")
        content = "\n\n".join(parts)

        return config.embedding.embed(
            [content],
            cache_dir=config.data_path / "embeddings",
            config=genai.types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
        )[0]
