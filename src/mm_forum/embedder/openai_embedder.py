from __future__ import annotations

import logging

from mm_forum.config import settings

logger = logging.getLogger(__name__)

_MAX_TEXTS_PER_CALL = 2048


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small embedder — higher quality, costs money."""

    def __init__(self, model: str | None = None) -> None:
        import openai

        self._model = model or settings.openai_model
        self._client = openai.OpenAI(api_key=settings.openai_api_key)
        logger.info("Using OpenAI embedding model: %s", self._model)

    @property
    def dimension(self) -> int:
        # text-embedding-3-small = 1536, text-embedding-3-large = 3072
        return 1536 if "small" in self._model else 3072

    @property
    def model_name(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), _MAX_TEXTS_PER_CALL):
            batch = texts[i : i + _MAX_TEXTS_PER_CALL]
            response = self._client.embeddings.create(input=batch, model=self._model)
            results.extend([item.embedding for item in response.data])
        return results
