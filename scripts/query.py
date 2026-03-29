#!/usr/bin/env python
"""Interactive semantic search CLI.

Usage:
    python scripts/query.py "how do I configure LDAP"
    python scripts/query.py "licensing changes" --limit 10
    python scripts/query.py --analytics feature-requests
    python scripts/query.py --analytics controversial
    python scripts/query.py --analytics active-users
    python scripts/query.py --analytics unanswered
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _print_search_results(results, query: str) -> None:
    table = Table(title=f'Search: "{query}"', show_lines=True)
    table.add_column("Score", style="cyan", width=6)
    table.add_column("Title", style="bold", width=40)
    table.add_column("User", width=15)
    table.add_column("Category", width=20)
    table.add_column("Likes", justify="right", width=6)
    table.add_column("Preview", width=60)

    for hit in results:
        p = hit.payload or {}
        table.add_row(
            f"{hit.score:.3f}",
            p.get("title", "")[:38],
            p.get("username", ""),
            p.get("category_name", "") or "",
            str(p.get("like_count", 0)),
            p.get("text_preview", "")[:58],
        )

    console.print(table)


@click.command()
@click.argument("query", required=False)
@click.option("--limit", default=20, show_default=True, help="Number of results")
@click.option("--model", default=None, type=click.Choice(["local", "openai"]))
@click.option(
    "--analytics",
    default=None,
    type=click.Choice(["feature-requests", "controversial", "active-users", "unanswered", "activity"]),
    help="Run a predefined analytics query instead of a search",
)
@click.option("--is-op", is_flag=True, default=False, help="Filter to first posts (OPs) only")
@click.option("--min-likes", default=None, type=int)
def main(
    query: str | None,
    limit: int,
    model: str | None,
    analytics: str | None,
    is_op: bool,
    min_likes: int | None,
) -> None:
    if analytics:
        _run_analytics(analytics, limit)
        return

    if not query:
        console.print("[red]Provide a query or --analytics flag[/red]")
        raise SystemExit(1)

    from mm_forum.pipeline.embed import get_embedder
    from mm_forum.analytics.semantic import semantic_search, find_feature_requests
    from mm_forum.vectordb.qdrant_store import QdrantStore

    embedder = get_embedder(model)
    store = QdrantStore()

    results = semantic_search(
        query=query,
        embedder=embedder,
        store=store,
        is_op=is_op if is_op else None,
        min_likes=min_likes,
        limit=limit,
    )
    _print_search_results(results, query)


def _run_analytics(analytics: str, limit: int) -> None:
    from mm_forum.analytics import aggregate

    if analytics == "controversial":
        df = aggregate.most_controversial_topics(top_n=limit)
        console.print(df.to_string(index=False))

    elif analytics == "active-users":
        df = aggregate.most_active_users(top_n=limit)
        console.print(df.to_string(index=False))

    elif analytics == "unanswered":
        df = aggregate.unanswered_questions(top_n=limit)
        console.print(df.to_string(index=False))

    elif analytics == "activity":
        df = aggregate.activity_over_time()
        console.print(df.to_string(index=False))

    elif analytics == "feature-requests":
        from mm_forum.pipeline.embed import get_embedder
        from mm_forum.analytics.semantic import find_feature_requests
        from mm_forum.vectordb.qdrant_store import QdrantStore

        embedder = get_embedder()
        store = QdrantStore()
        results = find_feature_requests(embedder=embedder, store=store, limit=limit)
        _print_search_results(results, "feature requests")


if __name__ == "__main__":
    main()
