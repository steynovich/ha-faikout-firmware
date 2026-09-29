import struct
from types import SimpleNamespace

import aiohttp
import pytest

from custom_components.faikout.ota.client import HEAD_BYTES, FaikoutOtaClient
from custom_components.faikout.ota.exceptions import (
    FirmwareFetchError,
    FirmwareParseError,
    FirmwareUnavailableError,
)

MAGIC = 0xABCD5432
MANIFEST = b'{"flash":[{"url":"https://x/app.bin","app":true}]}'


def _app_head():
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += b"1a347969".ljust(32, b"\x00") + b"Faikout".ljust(32, b"\x00")
    return body.ljust(HEAD_BYTES, b"\x00")


class FakeStream:
    """Stands in for aiohttp's StreamReader, recording how much was consumed."""

    def __init__(self, body):
        self._body = body
        self._pos = 0
        self.bytes_consumed = 0

    async def read(self, n=-1):
        # A real StreamReader may return fewer bytes than asked for; hand back at
        # most 100 at a time so the client has to loop to fill its buffer.
        want = len(self._body) if n < 0 else min(n, 100)
        chunk = self._body[self._pos : self._pos + want]
        self._pos += len(chunk)
        self.bytes_consumed += len(chunk)
        return chunk


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body
        self.content = FakeStream(body)
        self.full_body_reads = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        self.full_body_reads += 1
        return self._body

    async def text(self):
        return self._body.decode()

    def raise_for_status(self):
        if self.status >= 400:
            request_info = SimpleNamespace(real_url="https://m")
            raise aiohttp.ClientResponseError(request_info, (), status=self.status)


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        return self._responses.pop(0)

    async def close(self):
        self.closed = True


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


@pytest.mark.asyncio
async def test_injected_session_is_never_closed_by_the_client():
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(206, _app_head())])
    await FaikoutOtaClient(session).async_get_latest_version("https://m")
    assert session.closed is False


@pytest.mark.asyncio
async def test_full_get_fallback_when_range_ignored():
    full = b"\x00" * 32 + _app_head()
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(200, full)])
    client = FaikoutOtaClient(session)
    assert await client.async_get_latest_version("https://m") == "1a347969"


@pytest.mark.asyncio
async def test_range_ignored_response_does_not_buffer_the_whole_image():
    # A server that ignores Range answers 200 with the entire ~1.5 MB image; the
    # client must stop after HEAD_BYTES rather than pulling it all into memory.
    image = (b"\x00" * 32 + _app_head()).ljust(1_500_000, b"\xff")
    head = FakeResponse(200, image)
    session = FakeSession([FakeResponse(200, MANIFEST), head])

    assert await FaikoutOtaClient(session).async_get_latest_version("https://m") == "1a347969"
    assert head.full_body_reads == 0
    assert head.content.bytes_consumed == HEAD_BYTES


@pytest.mark.asyncio
async def test_short_body_stops_at_eof():
    # A truncated image ends the stream before HEAD_BYTES; the read loop must stop
    # on the empty chunk instead of spinning, and hand the short buffer to the parser.
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(206, _app_head()[:40])])
    with pytest.raises(FirmwareParseError):
        await FaikoutOtaClient(session).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_network_error_wrapped():
    class BoomSession:
        def get(self, url, headers=None, timeout=None):
            raise aiohttp.ClientError("boom")

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(BoomSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_connection_error_is_unavailable():
    class UnreachableSession:
        def get(self, url, headers=None, timeout=None):
            raise aiohttp.ClientConnectionError("no route to host")

    with pytest.raises(FirmwareUnavailableError):
        await FaikoutOtaClient(UnreachableSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_http_status_error_is_not_unavailable():
    # A 404 means the server answered; it is a broken URL, not an unreachable host,
    # and must stay distinguishable so the live e2e check fails instead of skipping.
    session = FakeSession([FakeResponse(404, b"")])
    with pytest.raises(FirmwareFetchError) as excinfo:
        await FaikoutOtaClient(session).async_get_latest_version("https://m")
    assert not isinstance(excinfo.value, FirmwareUnavailableError)


@pytest.mark.asyncio
async def test_timeout_wrapped():
    class TimeoutSession:
        def get(self, url, headers=None, timeout=None):
            raise TimeoutError

    with pytest.raises(FirmwareUnavailableError):
        await FaikoutOtaClient(TimeoutSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_head_fetch_error_wrapped():
    class ManifestThenBoomSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, headers=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(200, MANIFEST)
            raise aiohttp.ClientError("boom")

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(ManifestThenBoomSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_undecodable_manifest_body_is_a_fetch_error():
    session = FakeSession([FakeResponse(200, b"\xff\xfe not utf-8")])
    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(session).async_get_latest_version("https://m")
