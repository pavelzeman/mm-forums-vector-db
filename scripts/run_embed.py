#!/usr/bin/env python
"""Embed scraped posts into Qdrant.

Usage:
    python scripts/run_embed.py              # use default (local) embedder
    python scripts/run_embed.py --model openai
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from rich.logging import RichHandler

from mm_forum.pipeline.embed import run_embed

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(rich_tracebacks=True)])


@click.command()
@click.option("--model", default=None, type=click.Choice(["local", "openai"]), help="Embedding model to use")
def main(model: str | None) -> None:
    run_embed(model=model)


if __name__ == "__main__":
    main()
