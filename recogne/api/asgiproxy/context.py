import asyncio
from types import TracebackType
from typing import Optional, Self

import aiohttp

from .config import ProxyConfig


class ProxyContext:
    semaphore: asyncio.Semaphore
    _session: Optional[aiohttp.ClientSession] = None

    def __init__(
        self,
        config: ProxyConfig,
        max_concurrency: int = 20,
    ) -> None:
        self.config = config
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.DummyCookieJar(), auto_decompress=False
            )
        return self._session

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
