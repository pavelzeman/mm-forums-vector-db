from __future__ import annotations

import logging

from mm_forum.config import settings

logger = logging.getLogger(__name__)


class LocalEmbedder:
    """sentence-transformers embedder — runs on CPU/GPU locally, no API cost."""

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name or settings.local_model_name
        logger.info("Loading local embedding model: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)

    @property
    def dimension(self) -> int:
        return self._model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        # encode() returns ndarray in prod, but mocks may return a list
        return vectors.tolist() if hasattr(vectors, "tolist") else list(vectors)
