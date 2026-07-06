"""Async aiohttp client that resolves the latest firmware version."""

from __future__ import annotations

import aiohttp

from .exceptions import FirmwareFetchError
from .manifest import parse_manifest
from .parser import parse_app_descriptor

HEAD_BYTES = 512
DEFAULT_TIMEOUT = 30.0


class FaikoutOtaClient:
    """Fetch and parse the latest Faikout firmware version.

    The aiohttp session is injected and never closed by this client.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)

    async def async_get_latest_version(self, manifest_url: str) -> str:
        manifest_text = await self._get_text(manifest_url)
        app_url = parse_manifest(manifest_text)
        head = await self._get_head(app_url)
        return parse_app_descriptor(head)

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err

    async def _get_head(self, url: str) -> bytes:
        headers = {"Range": f"bytes=0-{HEAD_BYTES - 1}"}
        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as resp:
                resp.raise_for_status()
                body = await resp.read()
                if resp.status == 206:
                    return body
                return body[:HEAD_BYTES]
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err
