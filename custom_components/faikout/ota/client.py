"""Async aiohttp client that resolves the latest firmware version."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiohttp

from .exceptions import FirmwareFetchError, FirmwareUnavailableError
from .manifest import parse_manifest
from .parser import parse_app_descriptor

HEAD_BYTES = 512
DEFAULT_TIMEOUT = 30.0

_T = TypeVar("_T")


async def _read_head(resp: aiohttp.ClientResponse) -> bytes:
    """Read at most HEAD_BYTES from the response body.

    A server that ignores the Range header answers 200 with the whole ~1.5 MB
    image, so reading the full body would defeat the point of the ranged request.
    StreamReader.read(n) may return fewer than n bytes, hence the loop.
    """
    buf = bytearray()
    while len(buf) < HEAD_BYTES:
        chunk = await resp.content.read(HEAD_BYTES - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


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

    async def _fetch(
        self,
        url: str,
        reader: Callable[[aiohttp.ClientResponse], Awaitable[_T]],
        *,
        headers: dict[str, str] | None = None,
    ) -> _T:
        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as resp:
                resp.raise_for_status()
                return await reader(resp)
        except (aiohttp.ClientConnectionError, TimeoutError) as err:
            # The host never answered; retryable, and not a sign of a bad URL.
            raise FirmwareUnavailableError(f"failed to fetch {url}: {err}") from err
        except aiohttp.ClientError as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err

    async def _get_text(self, url: str) -> str:
        return await self._fetch(url, lambda resp: resp.text())

    async def _get_head(self, url: str) -> bytes:
        headers = {"Range": f"bytes=0-{HEAD_BYTES - 1}"}
        return await self._fetch(url, _read_head, headers=headers)
