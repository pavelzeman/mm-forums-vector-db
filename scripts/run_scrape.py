#!/usr/bin/env python
"""Scrape the Mattermost Discourse forum into PostgreSQL.

Usage:
    python scripts/run_scrape.py                        # scrape everything
    python scripts/run_scrape.py --category troubleshooting
    python scripts/run_scrape.py --posts-only           # skip topic discovery
    python scripts/run_scrape.py --limit 100            # stop after 100 topics
"""
import logging
import sys
from pathlib import Path

# Allow running from project root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from rich.logging import RichHandler

from mm_forum.pipeline.scrape import scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)


@click.command()
@click.option("--category", default=None, help="Scrape only this category slug (e.g. troubleshooting)")
@click.option("--posts-only", is_flag=True, default=False, help="Skip topic discovery, just fetch posts for pending topics")
@click.option("--limit", default=None, type=int, help="Stop after N topics (useful for testing)")
def main(category: str | None, posts_only: bool, limit: int | None) -> None:
    scrape(category=category, posts_only=posts_only, limit=limit)


if __name__ == "__main__":
    main()
