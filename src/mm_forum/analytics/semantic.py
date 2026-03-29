"""Semantic (vector) search queries against Qdrant."""
from __future__ import annotations

from qdrant_client.http.models import ScoredPoint

from mm_forum.embedder.base import Embedder
from mm_forum.vectordb.qdrant_store import QdrantStore, build_filter


def semantic_search(
    query: str,
    embedder: Embedder,
    store: QdrantStore,
    category_id: int | None = None,
    is_op: bool | None = None,
    min_likes: int | None = None,
    limit: int = 20,
) -> list[ScoredPoint]:
    """General-purpose semantic search with optional metadata filters."""
    vector = embedder.embed([query])[0]
    query_filter = build_filter(category_id=category_id, is_op=is_op, min_likes=min_likes)
    return store.search(query_vector=vector, query_filter=query_filter, limit=limit)


def find_feature_requests(
    embedder: Embedder,
    store: QdrantStore,
    limit: int = 50,
) -> list[ScoredPoint]:
    """Find posts that look like feature requests (OP-only for signal)."""
    probe = "I would like to request a new feature for Mattermost. It would be great if..."
    return semantic_search(query=probe, embedder=embedder, store=store, is_op=True, limit=limit)


def find_sentiment_on_topic(
    topic_phrase: str,
    embedder: Embedder,
    store: QdrantStore,
    limit: int = 50,
) -> list[ScoredPoint]:
    """Retrieve posts most semantically related to a topic phrase (e.g. 'licensing changes')."""
    return semantic_search(query=topic_phrase, embedder=embedder, store=store, limit=limit)


def find_similar_to_post(
    post_text: str,
    embedder: Embedder,
    store: QdrantStore,
    limit: int = 10,
) -> list[ScoredPoint]:
    """Find posts semantically similar to a given text."""
    return semantic_search(query=post_text, embedder=embedder, store=store, limit=limit)
