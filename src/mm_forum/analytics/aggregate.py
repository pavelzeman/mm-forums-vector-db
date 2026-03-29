"""SQL-backed aggregation analytics against PostgreSQL."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from mm_forum.db.store import _engine


def _query(sql: str, **params) -> pd.DataFrame:
    with _engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def most_active_users(top_n: int = 20) -> pd.DataFrame:
    """Users ranked by post count and total likes received."""
    return _query(
        """
        SELECT username,
               COUNT(*) AS post_count,
               SUM(like_count) AS total_likes,
               MAX(created_at) AS last_post_at
        FROM posts
        GROUP BY username
        ORDER BY post_count DESC
        LIMIT :n
        """,
        n=top_n,
    )


def most_controversial_topics(top_n: int = 20) -> pd.DataFrame:
    """Topics with high engagement (likes + replies) — a proxy for controversy."""
    return _query(
        """
        SELECT t.id, t.title, t.category_id, t.views,
               t.like_count, t.reply_count,
               t.posts_count,
               (t.like_count + t.reply_count * 2) AS engagement_score
        FROM topics t
        ORDER BY engagement_score DESC
        LIMIT :n
        """,
        n=top_n,
    )


def most_viewed_topics(top_n: int = 20) -> pd.DataFrame:
    return _query(
        """
        SELECT id, title, views, like_count, reply_count, created_at
        FROM topics
        ORDER BY views DESC
        LIMIT :n
        """,
        n=top_n,
    )


def unanswered_questions(top_n: int = 50) -> pd.DataFrame:
    """Open topics with no accepted answer and zero replies."""
    return _query(
        """
        SELECT t.id, t.title, t.created_at, t.views
        FROM topics t
        WHERE t.has_accepted_answer = false
          AND t.reply_count = 0
          AND t.closed = false
        ORDER BY t.views DESC
        LIMIT :n
        """,
        n=top_n,
    )


def activity_over_time(granularity: str = "month") -> pd.DataFrame:
    """Post volume over time. granularity: 'day', 'week', 'month', 'year'."""
    trunc = granularity.lower()
    allowed = {"day", "week", "month", "year"}
    if trunc not in allowed:
        raise ValueError(f"granularity must be one of {allowed}")
    return _query(
        f"""
        SELECT date_trunc('{trunc}', created_at) AS period,
               COUNT(*) AS post_count
        FROM posts
        WHERE created_at IS NOT NULL
        GROUP BY period
        ORDER BY period
        """
    )


def category_breakdown() -> pd.DataFrame:
    return _query(
        """
        SELECT c.name AS category,
               COUNT(DISTINCT t.id) AS topic_count,
               COUNT(p.id) AS post_count,
               SUM(p.like_count) AS total_likes
        FROM categories c
        LEFT JOIN topics t ON t.category_id = c.id
        LEFT JOIN posts p ON p.topic_id = t.id
        GROUP BY c.name
        ORDER BY post_count DESC
        """
    )


def top_liked_posts(top_n: int = 20) -> pd.DataFrame:
    return _query(
        """
        SELECT p.id, p.topic_id, t.title, p.username, p.like_count, p.post_number,
               LEFT(p.raw_text, 200) AS preview
        FROM posts p
        JOIN topics t ON t.id = p.topic_id
        ORDER BY p.like_count DESC
        LIMIT :n
        """,
        n=top_n,
    )
