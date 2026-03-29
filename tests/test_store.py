"""Integration tests for the PostgreSQL store — runs against a real DB."""
import pytest
from sqlalchemy import delete

from mm_forum.db.models import Category, Post, Topic
from mm_forum.db.store import (
    get_pending_topics,
    get_session,
    get_unembedded_posts,
    mark_posts_embedded,
    mark_topic_done,
    mark_topic_error,
    upsert_category,
    upsert_post,
    upsert_topic,
)

# Use IDs that are unlikely to collide with real forum data
_TEST_CATEGORY_ID = 9900
_TEST_TOPIC_ID = 9900000
_TEST_TOPIC_ID2 = 9900001
_TEST_POST_ID = 9900000


@pytest.fixture(autouse=True)
def clean_test_data():
    """Delete test rows before and after each test."""
    _delete_test_rows()
    yield
    _delete_test_rows()


def _delete_test_rows():
    with get_session() as s:
        s.execute(delete(Post).where(Post.id.in_([_TEST_POST_ID])))
        s.execute(delete(Topic).where(Topic.id.in_([_TEST_TOPIC_ID, _TEST_TOPIC_ID2])))
        s.execute(delete(Category).where(Category.id == _TEST_CATEGORY_ID))


@pytest.fixture()
def sample_category(session):
    upsert_category(session, {
        "id": _TEST_CATEGORY_ID,
        "name": "Test Cat",
        "slug": "test-cat-9900",
        "topic_count": 5,
    })
    return {"id": _TEST_CATEGORY_ID}


@pytest.fixture()
def sample_topic(session, sample_category):
    data = {
        "id": _TEST_TOPIC_ID,
        "title": "Test Topic",
        "slug": "test-topic-9900",
        "category_id": _TEST_CATEGORY_ID,
        "created_at": "2024-01-01T00:00:00Z",
        "last_posted_at": "2024-01-02T00:00:00Z",
        "posts_count": 3,
        "reply_count": 2,
        "views": 100,
        "like_count": 5,
    }
    upsert_topic(session, data)
    return data


@pytest.fixture()
def sample_post(session, sample_topic):
    data = {
        "id": _TEST_POST_ID,
        "topic_id": _TEST_TOPIC_ID,
        "post_number": 1,
        "username": "testuser",
        "user_id": 42,
        "trust_level": 1,
        "staff": False,
        "created_at": "2024-01-01T00:00:00Z",
        "raw": "Hello world",
        "cooked": "<p>Hello world</p>",
        "actions_summary": [{"id": 2, "count": 3}],
        "reply_count": 0,
        "reads": 10,
        "score": 1.5,
    }
    upsert_post(session, data)
    return data


def test_upsert_topic_creates_pending(session, sample_topic):
    pending = get_pending_topics(session)
    ids = [t.id for t in pending]
    assert _TEST_TOPIC_ID in ids


def test_mark_topic_done_removes_from_pending(session, sample_topic):
    mark_topic_done(session, _TEST_TOPIC_ID)
    pending = get_pending_topics(session)
    ids = [t.id for t in pending]
    assert _TEST_TOPIC_ID not in ids


def test_mark_topic_error(session, sample_topic):
    mark_topic_error(session, _TEST_TOPIC_ID)
    pending = get_pending_topics(session)
    ids = [t.id for t in pending]
    assert _TEST_TOPIC_ID not in ids


def test_upsert_topic_is_idempotent(session):
    data = {
        "id": _TEST_TOPIC_ID2,
        "title": "Idempotent Topic",
        "slug": "idempotent-topic-9900",
        "category_id": None,
        "created_at": "2024-02-01T00:00:00Z",
    }
    upsert_topic(session, data)
    upsert_topic(session, data)  # second call should not raise or duplicate
    pending = get_pending_topics(session)
    topic_ids = [t.id for t in pending]
    assert topic_ids.count(_TEST_TOPIC_ID2) == 1


def test_upsert_post_extracts_like_count(session, sample_post):
    unembedded = get_unembedded_posts(session)
    post = next((p for p in unembedded if p.id == _TEST_POST_ID), None)
    assert post is not None
    assert post.like_count == 3  # from actions_summary id=2


def test_mark_posts_embedded(session, sample_post):
    unembedded_before = get_unembedded_posts(session)
    assert any(p.id == _TEST_POST_ID for p in unembedded_before)

    mark_posts_embedded(session, [_TEST_POST_ID])
    unembedded_after = get_unembedded_posts(session)
    assert all(p.id != _TEST_POST_ID for p in unembedded_after)


def test_upsert_category(session):
    upsert_category(session, {"id": _TEST_CATEGORY_ID, "name": "Scratch", "slug": "scratch-9900", "topic_count": 0})
    # Idempotent second call
    upsert_category(session, {"id": _TEST_CATEGORY_ID, "name": "Scratch Updated", "slug": "scratch-9900", "topic_count": 1})
