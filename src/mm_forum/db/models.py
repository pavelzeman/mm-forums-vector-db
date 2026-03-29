from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    topic_count: Mapped[int] = mapped_column(Integer, default=0)

    topics: Mapped[list["Topic"]] = relationship("Topic", back_populates="category")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index("ix_topics_scrape_status", "scrape_status"),
        Index("ix_topics_category_id", "category_id"),
        Index("ix_topics_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    has_accepted_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    scrape_status: Mapped[str] = mapped_column(Text, default="pending")  # pending/done/error
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped["Category | None"] = relationship("Category", back_populates="topics")
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="topic")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_topic_id", "topic_id"),
        Index("ix_posts_embedded", "embedded"),
        Index("ix_posts_username", "username"),
        Index("ix_posts_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("topics.id"), nullable=False)
    post_number: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_level: Mapped[int] = mapped_column(Integer, default=0)
    staff: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cooked_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to_post_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    reads: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    accepted_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    embedded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_server: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    topic: Mapped["Topic"] = relationship("Topic", back_populates="posts")
