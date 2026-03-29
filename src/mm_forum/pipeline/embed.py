import logging

from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from mm_forum.config import settings
from mm_forum.db.models import Post, Topic
from mm_forum.db.store import (
    get_session,
    get_topic_by_id,
    get_unembedded_posts,
    mark_posts_embedded,
)
from mm_forum.embedder.base import Embedder
from mm_forum.scraper.posts import extract_post_text
from mm_forum.vectordb.qdrant_store import QdrantStore, build_point

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 64


def _build_embed_text(post: Post, topic: Topic) -> str:
    text = extract_post_text({"raw": post.raw_text, "cooked": post.cooked_html})
    if post.post_number == 1:
        return f"{topic.title}\n\n{text}"
    return text


def get_embedder(model: str | None = None) -> Embedder:
    model = model or settings.embedding_model
    if model == "openai":
        from mm_forum.embedder.openai_embedder import OpenAIEmbedder
        return OpenAIEmbedder()
    from mm_forum.embedder.local import LocalEmbedder
    return LocalEmbedder()


def run_embed(model: str | None = None) -> None:
    """Embed all unembedded posts from Postgres into Qdrant."""
    embedder = get_embedder(model)
    store = QdrantStore()
    store.ensure_collection(embedder.dimension)

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Embedding posts...", total=None)
        total = 0

        while True:
            with get_session() as session:
                posts = get_unembedded_posts(session, batch_size=_EMBED_BATCH_SIZE)

            if not posts:
                break

            # Load topics for the batch (needed for payload)
            topic_cache: dict[int, Topic] = {}
            with get_session() as session:
                for post in posts:
                    if post.topic_id not in topic_cache:
                        topic = get_topic_by_id(session, post.topic_id)
                        if topic:
                            # Eagerly load category to avoid detached instance errors
                            _ = topic.category
                            session.expunge(topic)
                            if topic.category:
                                session.expunge(topic.category)
                            topic_cache[post.topic_id] = topic

            # Build embed texts
            valid_posts = [p for p in posts if p.topic_id in topic_cache]
            texts = [_build_embed_text(p, topic_cache[p.topic_id]) for p in valid_posts]

            if not texts:
                with get_session() as session:
                    mark_posts_embedded(session, [p.id for p in posts])
                continue

            vectors = embedder.embed(texts)

            points = [
                build_point(post, topic_cache[post.topic_id], vector)
                for post, vector in zip(valid_posts, vectors)
            ]
            store.upsert(points)

            with get_session() as session:
                mark_posts_embedded(session, [p.id for p in posts])

            total += len(valid_posts)
            progress.update(task, advance=len(valid_posts), description=f"Embedded {total} posts...")

    logger.info("Embedding complete: %d posts embedded into Qdrant", total)
