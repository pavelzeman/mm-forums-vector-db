import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from bs4 import BeautifulSoup

from mm_forum.scraper.client import RateLimitedClient

logger = logging.getLogger(__name__)

_POST_BATCH_SIZE = 20  # Discourse returns at most 20 posts per chunk


@dataclass
class FullTopic:
    topic_id: int
    slug: str
    posts: list[dict]
    post_stream_ids: list[int]


def extract_post_text(post: dict) -> str:
    """Return clean text: prefer raw markdown, fallback to stripped HTML."""
    raw = (post.get("raw") or "").strip()
    if raw:
        return raw
    cooked = post.get("cooked") or ""
    return BeautifulSoup(cooked, "lxml").get_text(separator=" ").strip()


async def fetch_topic_with_posts(
    client: RateLimitedClient,
    topic_id: int,
    slug: str,
) -> FullTopic | None:
    """Fetch all posts in a topic, handling pagination in batches of 20."""
    data = await client.get(f"/t/{slug}/{topic_id}.json")
    if not data:
        return None

    post_stream = data.get("post_stream", {})
    initial_posts: list[dict] = post_stream.get("posts", [])
    all_stream_ids: list[int] = post_stream.get("stream", [])

    # Augment each post with topic_id (may be missing in post payload)
    for post in initial_posts:
        post["topic_id"] = topic_id

    # IDs already fetched in the first response
    fetched_ids = {p["id"] for p in initial_posts}
    remaining_ids = [pid for pid in all_stream_ids if pid not in fetched_ids]

    all_posts = list(initial_posts)
    all_posts.extend(await _fetch_post_batches(client, topic_id, slug, remaining_ids))

    return FullTopic(
        topic_id=topic_id,
        slug=slug,
        posts=all_posts,
        post_stream_ids=all_stream_ids,
    )


async def _fetch_post_batches(
    client: RateLimitedClient,
    topic_id: int,
    slug: str,
    post_ids: list[int],
) -> list[dict]:
    posts: list[dict] = []
    for i in range(0, len(post_ids), _POST_BATCH_SIZE):
        batch = post_ids[i : i + _POST_BATCH_SIZE]
        params = {"post_ids[]": batch}  # httpx serialises list params correctly
        data = await client.get(f"/t/{slug}/{topic_id}.json", params=params)
        chunk = data.get("post_stream", {}).get("posts", [])
        for post in chunk:
            post["topic_id"] = topic_id
        posts.extend(chunk)
        logger.debug("Topic %d: fetched %d/%d posts", topic_id, len(posts), len(post_ids))
    return posts


async def iter_topic_posts(
    client: RateLimitedClient,
    topic_id: int,
    slug: str,
) -> AsyncIterator[dict]:
    """Async iterator yielding individual post dicts for a topic."""
    full = await fetch_topic_with_posts(client, topic_id, slug)
    if full:
        for post in full.posts:
            yield post
