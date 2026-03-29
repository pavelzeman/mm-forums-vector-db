import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mm_forum.scraper.client import RateLimitedClient

logger = logging.getLogger(__name__)


@dataclass
class CategoryInfo:
    id: int
    name: str
    slug: str
    topic_count: int


async def fetch_all_categories(client: RateLimitedClient) -> list[CategoryInfo]:
    data = await client.get("/categories.json")
    categories = []
    for cat in data.get("category_list", {}).get("categories", []):
        categories.append(
            CategoryInfo(
                id=cat["id"],
                name=cat["name"],
                slug=cat["slug"],
                topic_count=cat.get("topic_count", 0),
            )
        )
    logger.info("Found %d categories", len(categories))
    return categories


async def fetch_topics_for_category(
    client: RateLimitedClient,
    category: CategoryInfo,
) -> AsyncIterator[dict]:
    """Yield raw topic dicts for one category, paginating until exhausted."""
    page = 0
    seen = 0
    while True:
        path = f"/c/{category.slug}/{category.id}/l/latest.json"
        data = await client.get(path, params={"page": page})
        topic_list = data.get("topic_list", {})
        topics = topic_list.get("topics", [])

        if not topics:
            break

        for topic in topics:
            # Attach category info since it's not always in the topic payload
            topic.setdefault("category_id", category.id)
            yield topic
            seen += 1

        logger.debug("Category %s page %d: %d topics (total seen: %d)", category.slug, page, len(topics), seen)

        if "more_topics_url" not in topic_list:
            break

        page += 1


async def fetch_all_topics(client: RateLimitedClient) -> AsyncIterator[tuple[CategoryInfo, dict]]:
    """Yield (category, topic_dict) for every topic across all categories."""
    categories = await fetch_all_categories(client)
    for category in categories:
        logger.info("Scraping category: %s (%d topics expected)", category.name, category.topic_count)
        async for topic in fetch_topics_for_category(client, category):
            yield category, topic
