from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from mm_forum.config import settings
from mm_forum.db.models import Base, Category, Post, Topic

_engine = create_engine(settings.database_url, pool_pre_ping=True)
_SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)


def create_engine_from_url(url: str):
    """Create a new engine — used in tests to inject test DB URL."""
    global _engine, _SessionFactory
    _engine = create_engine(url, pool_pre_ping=True)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Create all tables if they don't exist (used in tests; prod uses Alembic)."""
    Base.metadata.create_all(_engine, checkfirst=True)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------

def upsert_category(session: Session, data: dict) -> None:
    stmt = (
        insert(Category)
        .values(id=data["id"], name=data["name"], slug=data["slug"], topic_count=data.get("topic_count", 0))
        .on_conflict_do_update(
            index_elements=["id"],
            set_={"name": data["name"], "slug": data["slug"], "topic_count": data.get("topic_count", 0)},
        )
    )
    session.execute(stmt)


# ---------------------------------------------------------------------------
# Topic helpers
# ---------------------------------------------------------------------------

def upsert_topic(session: Session, data: dict) -> None:
    values = {
        "id": data["id"],
        "title": data["title"],
        "slug": data["slug"],
        "category_id": data.get("category_id"),
        "created_at": _parse_dt(data.get("created_at")),
        "last_posted_at": _parse_dt(data.get("last_posted_at")),
        "posts_count": data.get("posts_count", 0),
        "reply_count": data.get("reply_count", 0),
        "views": data.get("views", 0),
        "like_count": data.get("like_count", 0),
        "has_accepted_answer": bool(data.get("has_accepted_answer", False)),
        "pinned": bool(data.get("pinned", False)),
        "closed": bool(data.get("closed", False)),
        "archived": bool(data.get("archived", False)),
        "scrape_status": "pending",
    }
    stmt = (
        insert(Topic)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["id"],
            set_={k: v for k, v in values.items() if k not in ("id", "scrape_status")},
        )
    )
    session.execute(stmt)


def get_pending_topics(session: Session, limit: int = 100) -> list[Topic]:
    return list(
        session.scalars(
            select(Topic).where(Topic.scrape_status == "pending").limit(limit)
        )
    )


def mark_topic_done(session: Session, topic_id: int) -> None:
    session.execute(
        update(Topic)
        .where(Topic.id == topic_id)
        .values(scrape_status="done", scraped_at=datetime.now(timezone.utc))
    )


def mark_topic_error(session: Session, topic_id: int) -> None:
    session.execute(
        update(Topic).where(Topic.id == topic_id).values(scrape_status="error")
    )


# ---------------------------------------------------------------------------
# Post helpers
# ---------------------------------------------------------------------------

def upsert_post(session: Session, data: dict) -> None:
    like_count = 0
    for action in data.get("actions_summary", []):
        if action.get("id") == 2:  # 2 = like
            like_count = action.get("count", 0)
            break

    values = {
        "id": data["id"],
        "topic_id": data["topic_id"],
        "post_number": data["post_number"],
        "username": data.get("username", ""),
        "user_id": data.get("user_id"),
        "trust_level": data.get("trust_level", 0),
        "staff": bool(data.get("staff", False)),
        "created_at": _parse_dt(data.get("created_at")),
        "updated_at": _parse_dt(data.get("updated_at")),
        "raw_text": data.get("raw"),
        "cooked_html": data.get("cooked"),
        "reply_to_post_number": data.get("reply_to_post_number"),
        "reply_count": data.get("reply_count", 0),
        "like_count": like_count,
        "reads": data.get("reads", 0),
        "score": float(data.get("score", 0.0)),
        "accepted_answer": bool(data.get("accepted_answer", False)),
        "embedded": False,
    }
    stmt = (
        insert(Post)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["id"],
            set_={k: v for k, v in values.items() if k not in ("id", "embedded")},
        )
    )
    session.execute(stmt)


def get_unembedded_posts(session: Session, batch_size: int = 64) -> list[Post]:
    return list(
        session.scalars(
            select(Post).where(Post.embedded == False).limit(batch_size)  # noqa: E712
        )
    )


def mark_posts_embedded(session: Session, post_ids: list[int]) -> None:
    session.execute(
        update(Post).where(Post.id.in_(post_ids)).values(embedded=True)
    )


def get_topic_by_id(session: Session, topic_id: int) -> Topic | None:
    return session.get(Topic, topic_id)


def get_posts_by_ids(session: Session, post_ids: list[int]) -> list[Post]:
    return list(session.scalars(select(Post).where(Post.id.in_(post_ids))))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
