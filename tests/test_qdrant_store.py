"""Integration tests for QdrantStore — uses a real testcontainers Qdrant instance."""
import pytest
from qdrant_client.http.models import PointStruct

from mm_forum.vectordb.qdrant_store import QdrantStore, build_filter

TEST_COLLECTION = "test_mm_forum"


@pytest.fixture(scope="module")
def store(qdrant_url):
    s = QdrantStore(url=qdrant_url, collection=TEST_COLLECTION)
    # Clean up from previous run if exists
    try:
        s.delete_collection()
    except Exception:
        pass
    s.ensure_collection(dimension=4)
    yield s
    try:
        s.delete_collection()
    except Exception:
        pass


def test_ensure_collection_is_idempotent(store):
    # Calling ensure_collection again should not raise
    store.ensure_collection(dimension=4)


def test_upsert_and_search(store):
    points = [
        PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"username": "alice", "like_count": 5, "is_op": True, "category_id": 1, "created_at_ts": 1000}),
        PointStruct(id=2, vector=[0.0, 1.0, 0.0, 0.0], payload={"username": "bob", "like_count": 1, "is_op": False, "category_id": 2, "created_at_ts": 2000}),
        PointStruct(id=3, vector=[0.9, 0.1, 0.0, 0.0], payload={"username": "carol", "like_count": 10, "is_op": True, "category_id": 1, "created_at_ts": 3000}),
    ]
    store.upsert(points)

    results = store.search(query_vector=[1.0, 0.0, 0.0, 0.0], limit=3)
    assert len(results) > 0
    assert results[0].id in (1, 3)  # both are close to [1,0,0,0]


def test_search_with_filter(store):
    results = store.search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=build_filter(is_op=True),
        limit=5,
    )
    assert all(r.payload.get("is_op") is True for r in results)


def test_search_with_min_likes_filter(store):
    results = store.search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=build_filter(min_likes=5),
        limit=5,
    )
    assert all(r.payload.get("like_count", 0) >= 5 for r in results)


def test_search_with_category_filter(store):
    results = store.search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=build_filter(category_id=1),
        limit=5,
    )
    assert all(r.payload.get("category_id") == 1 for r in results)


def test_count(store):
    count = store.count()
    assert count >= 3


def test_build_filter_none_when_no_args():
    assert build_filter() is None
