import asyncio
import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mm_forum.config import settings

logger = logging.getLogger(__name__)


class RateLimitedClient:
    """Async HTTP client with politeness delay and retry on 429/5xx."""

    def __init__(
        self,
        base_url: str = "",
        delay_seconds: float | None = None,
    ) -> None:
        self._base_url = base_url or settings.forum_base_url
        self._delay = delay_seconds if delay_seconds is not None else settings.scrape_delay_seconds
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Accept": "application/json", "User-Agent": "mm-forum-scraper/0.1"},
            timeout=30.0,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "RateLimitedClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    async def get(self, path: str, params: dict | None = None) -> dict:
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        response = await self._client.get(path, params=params)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            logger.warning("Rate limited — sleeping %ds", retry_after)
            await asyncio.sleep(retry_after)
            response.raise_for_status()

        if response.status_code == 404:
            logger.debug("404 for %s — skipping", path)
            return {}

        response.raise_for_status()
        return response.json()
