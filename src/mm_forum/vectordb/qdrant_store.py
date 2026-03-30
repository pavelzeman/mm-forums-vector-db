from __future__ import annotations

import logging
from datetime import timezone

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    OptimizersConfigDiff,
    PayloadSchemaType,
    PointStruct,
    Range,
    ScoredPoint,
    VectorParams,
)

from mm_forum.config import settings
from mm_forum.db.models import Post, Topic
from mm_forum.scraper.posts import extract_post_text

logger = logging.getLogger(__name__)

_PAYLOAD_INDICES = [
    ("category_id", PayloadSchemaType.INTEGER),
    ("created_at_ts", PayloadSchemaType.INTEGER),
    ("like_count", PayloadSchemaType.INTEGER),
    ("username", PayloadSchemaType.KEYWORD),
    ("is_op", PayloadSchemaType.BOOL),
]


class QdrantStore:
    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self._url = url or settings.qdrant_url
        self._collection = collection or settings.qdrant_collection
        self._client = QdrantClient(url=self._url)

    @property
    def collection(self) -> str:
        return self._collection

    def ensure_collection(self, dimension: int) -> None:
        """Create the collection and payload indices if they don't exist."""
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
                optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d)", self._collection, dimension)

            for field_name, field_type in _PAYLOAD_INDICES:
                self._client.create_payload_index(self._collection, field_name, field_type)
            logger.info("Created %d payload indices", len(_PAYLOAD_INDICES))
        else:
            logger.info("Collection '%s' already exists", self._collection)

    def upsert(self, points: list[PointStruct], batch_size: int = 500) -> None:
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(collection_name=self._collection, points=batch, wait=True)
        logger.debug("Upserted %d points", len(points))

    def search(
        self,
        query_vector: list[float],
        query_filter: Filter | None = None,
        limit: int = 20,
    ) -> list[ScoredPoint]:
        result = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return result.points

    def count(self) -> int:
        return self._client.count(collection_name=self._collection).count

    def delete_collection(self) -> None:
        self._client.delete_collection(self._collection)


def build_point(post: Post, topic: Topic, vector: list[float]) -> PointStruct:
    """Convert a Post + Topic into a Qdrant PointStruct."""
    is_op = post.post_number == 1
    text = extract_post_text({"raw": post.raw_text, "cooked": post.cooked_html})

    created_ts = 0
    if post.created_at:
        created_ts = int(post.created_at.replace(tzinfo=timezone.utc).timestamp())

    topic_created_ts = 0
    if topic.created_at:
        topic_created_ts = int(topic.created_at.replace(tzinfo=timezone.utc).timestamp())

    payload = {
        "post_id": post.id,
        "topic_id": post.topic_id,
        "topic_slug": topic.slug,
        "post_number": post.post_number,
        "title": topic.title,
        "username": post.username,
        "user_id": post.user_id,
        "trust_level": post.trust_level,
        "is_staff": post.staff,
        "category_id": topic.category_id,
        "category_name": topic.category.name if topic.category else None,
        "created_at_ts": created_ts,
        "like_count": post.like_count,
        "reply_count": post.reply_count,
        "reads": post.reads,
        "score": post.score,
        "is_op": is_op,
        "accepted_answer": post.accepted_answer,
        "topic_views": topic.views,
        "topic_posts_count": topic.posts_count,
        "topic_like_count": topic.like_count,
        "topic_created_at_ts": topic_created_ts,
        "closed": topic.closed,
        "text_preview": text[:300],
    }

    return PointStruct(id=post.id, vector=vector, payload=payload)


def build_filter(
    category_id: int | None = None,
    username: str | None = None,
    is_op: bool | None = None,
    min_likes: int | None = None,
    date_from_ts: int | None = None,
    date_to_ts: int | None = None,
) -> Filter | None:
    conditions = []

    if category_id is not None:
        conditions.append(FieldCondition(key="category_id", match=MatchValue(value=category_id)))
    if username is not None:
        conditions.append(FieldCondition(key="username", match=MatchValue(value=username)))
    if is_op is not None:
        conditions.append(FieldCondition(key="is_op", match=MatchValue(value=is_op)))
    if min_likes is not None:
        conditions.append(FieldCondition(key="like_count", range=Range(gte=min_likes)))
    if date_from_ts is not None or date_to_ts is not None:
        conditions.append(
            FieldCondition(
                key="created_at_ts",
                range=Range(gte=date_from_ts, lte=date_to_ts),
            )
        )

    return Filter(must=conditions) if conditions else None
