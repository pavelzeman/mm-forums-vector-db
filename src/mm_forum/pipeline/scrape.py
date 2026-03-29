import asyncio
import logging

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from mm_forum.db.store import (
    get_pending_topics,
    get_session,
    mark_topic_done,
    mark_topic_error,
    upsert_category,
    upsert_post,
    upsert_topic,
)
from mm_forum.scraper.client import RateLimitedClient
from mm_forum.scraper.posts import fetch_topic_with_posts
from mm_forum.scraper.topics import (
    fetch_all_categories,
    fetch_topics_for_category,
)

logger = logging.getLogger(__name__)


async def run_topic_discovery(category_slug: str | None = None) -> None:
    """Phase 1: discover all topics and insert them with scrape_status='pending'."""
    async with RateLimitedClient() as client:
        all_categories = await fetch_all_categories(client)

        with get_session() as session:
            for cat in all_categories:
                upsert_category(session, {"id": cat.id, "name": cat.name, "slug": cat.slug, "topic_count": cat.topic_count})

        categories = all_categories
        if category_slug:
            categories = [c for c in all_categories if c.slug == category_slug]
            if not categories:
                raise ValueError(f"Category '{category_slug}' not found. Available: {[c.slug for c in all_categories]}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            for category in categories:
                task = progress.add_task(f"Discovering {category.name}...", total=None)
                count = 0
                async for topic in fetch_topics_for_category(client, category):
                    with get_session() as session:
                        upsert_topic(session, topic)
                    count += 1
                    progress.update(task, description=f"Discovering {category.name} ({count} topics)...")
                progress.update(task, description=f"[green]{category.name}: {count} topics discovered")

    logger.info("Topic discovery complete")


async def run_post_scrape(limit: int | None = None) -> None:
    """Phase 2: fetch all posts for pending topics."""
    async with RateLimitedClient() as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Fetching posts...", total=None)
            total_done = 0
            total_errors = 0

            while True:
                with get_session() as session:
                    pending = get_pending_topics(session, limit=50)

                if not pending:
                    break

                for topic in pending:
                    progress.update(
                        task,
                        description=f"Fetching posts: {topic.id} '{topic.title[:50]}' (done={total_done}, errors={total_errors})",
                    )
                    try:
                        full = await fetch_topic_with_posts(client, topic.id, topic.slug)
                        if full:
                            with get_session() as session:
                                for post in full.posts:
                                    upsert_post(session, post)
                                mark_topic_done(session, topic.id)
                            total_done += 1
                        else:
                            with get_session() as session:
                                mark_topic_error(session, topic.id)
                            total_errors += 1
                    except Exception as exc:
                        logger.error("Error fetching topic %d: %s", topic.id, exc)
                        with get_session() as session:
                            mark_topic_error(session, topic.id)
                        total_errors += 1

                if limit and total_done >= limit:
                    break

    logger.info("Post scrape complete: %d done, %d errors", total_done, total_errors)


def scrape(category: str | None = None, posts_only: bool = False, limit: int | None = None) -> None:
    """Entry point: runs topic discovery then post scraping."""
    if not posts_only:
        asyncio.run(run_topic_discovery(category_slug=category))
    asyncio.run(run_post_scrape(limit=limit))
