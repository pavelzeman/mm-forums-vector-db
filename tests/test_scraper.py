"""Unit tests for the scraper — HTTP is mocked with respx."""
import httpx
import pytest
import respx

from mm_forum.scraper.client import RateLimitedClient
from mm_forum.scraper.posts import extract_post_text, fetch_topic_with_posts
from mm_forum.scraper.topics import (
    CategoryInfo,
    fetch_all_categories,
    fetch_topics_for_category,
)

FORUM_URL = "https://forum.mattermost.com"


@pytest.fixture
def mock_client():
    """Return a RateLimitedClient with zero delay for tests."""
    return RateLimitedClient(base_url=FORUM_URL, delay_seconds=0)


@respx.mock
async def test_fetch_all_categories(mock_client):
    respx.get(f"{FORUM_URL}/categories.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "category_list": {
                    "categories": [
                        {"id": 1, "name": "General", "slug": "general", "topic_count": 42},
                        {"id": 2, "name": "Bugs", "slug": "bugs", "topic_count": 7},
                    ]
                }
            },
        )
    )
    async with mock_client:
        categories = await fetch_all_categories(mock_client)

    assert len(categories) == 2
    assert categories[0].name == "General"
    assert categories[1].slug == "bugs"


@respx.mock
async def test_fetch_topics_for_category_pagination(mock_client):
    category = CategoryInfo(id=1, name="General", slug="general", topic_count=2)

    # First page (page=0): has more_topics_url → continue
    respx.get(f"{FORUM_URL}/c/general/1/l/latest.json", params={"page": 0}).mock(
        return_value=httpx.Response(
            200,
            json={
                "topic_list": {
                    "more_topics_url": "/c/general/1/l/latest?page=1",
                    "topics": [{"id": 101, "title": "Topic A", "slug": "topic-a", "category_id": 1}],
                }
            },
        )
    )
    # Second page (page=1): no more_topics_url → stop
    respx.get(f"{FORUM_URL}/c/general/1/l/latest.json", params={"page": 1}).mock(
        return_value=httpx.Response(
            200,
            json={
                "topic_list": {
                    "topics": [{"id": 102, "title": "Topic B", "slug": "topic-b", "category_id": 1}],
                }
            },
        )
    )

    async with mock_client:
        topics = [t async for t in fetch_topics_for_category(mock_client, category)]

    assert len(topics) == 2
    assert topics[0]["id"] == 101
    assert topics[1]["id"] == 102


@respx.mock
async def test_fetch_topic_with_posts(mock_client):
    respx.get(f"{FORUM_URL}/t/hello-world/42.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "post_stream": {
                    "posts": [
                        {
                            "id": 1001,
                            "post_number": 1,
                            "username": "alice",
                            "raw": "Hello world!",
                            "cooked": "<p>Hello world!</p>",
                            "actions_summary": [],
                        }
                    ],
                    "stream": [1001],
                }
            },
        )
    )

    async with mock_client:
        full = await fetch_topic_with_posts(mock_client, topic_id=42, slug="hello-world")

    assert full is not None
    assert full.topic_id == 42
    assert len(full.posts) == 1
    assert full.posts[0]["username"] == "alice"


def test_extract_post_text_prefers_raw():
    post = {"raw": "## Hello\n\nThis is **raw** text.", "cooked": "<h2>Hello</h2><p>This is raw text.</p>"}
    result = extract_post_text(post)
    assert "## Hello" in result


def test_extract_post_text_fallback_to_cooked():
    post = {"raw": None, "cooked": "<p>Hello from HTML</p>"}
    result = extract_post_text(post)
    assert "Hello from HTML" in result


def test_extract_post_text_empty():
    result = extract_post_text({"raw": None, "cooked": None})
    assert result == ""
