import struct

import aiohttp
import pytest

from custom_components.faikout.ota.client import FaikoutOtaClient, HEAD_BYTES
from custom_components.faikout.ota.exceptions import FirmwareFetchError

MAGIC = 0xABCD5432
MANIFEST = b'{"flash":[{"url":"https://x/app.bin","app":true}]}'


def _app_head():
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += b"1a347969".ljust(32, b"\x00") + b"Faikout".ljust(32, b"\x00")
    return body.ljust(HEAD_BYTES, b"\x00")


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode()

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientError(f"status {self.status}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_happy_path_uses_range():
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(206, _app_head())])
    client = FaikoutOtaClient(session)
    version = await client.async_get_latest_version("https://m/manifest.json")

    assert version == "1a347969"
    assert session.calls[0][0] == "https://m/manifest.json"
    assert session.calls[1][0] == "https://x/app.bin"
    assert session.calls[1][1]["Range"] == "bytes=0-511"
    assert session.calls[1][2].total == 30.0
    assert session.closed is False


@pytest.mark.asyncio
async def test_full_get_fallback_when_range_ignored():
    full = b"\x00" * 32 + _app_head()
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(200, full)])
    client = FaikoutOtaClient(session)
    assert await client.async_get_latest_version("https://m") == "1a347969"


@pytest.mark.asyncio
async def test_network_error_wrapped():
    class BoomSession:
        def get(self, url, headers=None, timeout=None):
            raise aiohttp.ClientError("boom")

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(BoomSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_timeout_wrapped():
    class TimeoutSession:
        def get(self, url, headers=None, timeout=None):
            raise TimeoutError

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(TimeoutSession()).async_get_latest_version("https://m")
