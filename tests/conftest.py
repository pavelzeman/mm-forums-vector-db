"""Shared pytest fixtures.

Strategy:
- If DATABASE_URL / QDRANT_URL env vars are set (local dev with docker compose, or CI services),
  use them directly — no testcontainers needed.
- If not set, spin up real containers via testcontainers (useful for isolated runs).
"""
import os

import pytest

# On macOS with Docker Desktop, the socket may not be at /var/run/docker.sock
_MAC_DOCKER_SOCK = os.path.expanduser("~/.docker/run/docker.sock")
if not os.environ.get("DOCKER_HOST") and os.path.exists(_MAC_DOCKER_SOCK):
    os.environ["DOCKER_HOST"] = f"unix://{_MAC_DOCKER_SOCK}"

# Disable Ryuk (testcontainers reaper) — not reliably available with all Docker Desktop setups
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

_ENV_DB_URL = os.environ.get("DATABASE_URL")
_ENV_QDRANT_URL = os.environ.get("QDRANT_URL")


@pytest.fixture(scope="session")
def db_url():
    if _ENV_DB_URL:
        yield _ENV_DB_URL
        return
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def qdrant_url():
    if _ENV_QDRANT_URL:
        yield _ENV_QDRANT_URL
        return
    from testcontainers.qdrant import QdrantContainer
    with QdrantContainer("qdrant/qdrant:latest") as qdrant:
        yield f"http://{qdrant.get_container_host_ip()}:{qdrant.get_exposed_port(6333)}"


@pytest.fixture(scope="session", autouse=True)
def setup_db(db_url):
    """Create tables once per test session."""
    from mm_forum.db.store import create_engine_from_url, init_db
    create_engine_from_url(db_url)
    init_db()


@pytest.fixture()
def session(setup_db):
    """DB session per test."""
    from mm_forum.db.store import get_session
    with get_session() as s:
        yield s
