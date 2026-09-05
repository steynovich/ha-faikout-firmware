"""Live end-to-end check against the real Faikout OTA server.

Marked `network` so it is excluded from the default (offline) test run; it
skips cleanly if the OTA server is unreachable.
"""

import aiohttp
import pytest
import pytest_socket

from custom_components.faikout.const import Channel, manifest_url_for
from custom_components.faikout.ota.client import FaikoutOtaClient
from custom_components.faikout.ota.exceptions import FirmwareUnavailableError


@pytest.mark.network
@pytest.mark.parametrize("channel", [Channel.STABLE, Channel.BETA])
async def test_live_version_is_nonempty(channel, socket_enabled):
    # pytest-homeassistant-custom-component restricts sockets to 127.0.0.1 for
    # every test by default; the `socket_enabled` fixture lifts the blanket
    # socket ban, and this call lifts the host allow-list for the real OTA host.
    pytest_socket.socket_allow_hosts(["ota.faikout.uk"], allow_unix_socket=True)
    url = manifest_url_for("Faikout-S3-MINI-N4-R2", channel)
    assert url is not None
    try:
        async with aiohttp.ClientSession() as session:
            version = await FaikoutOtaClient(session).async_get_latest_version(url)
    except (aiohttp.ClientConnectionError, FirmwareUnavailableError) as err:
        # Only an unreachable host is an environment problem worth skipping. A 404
        # or a malformed manifest is a real defect and must fail the run: a blanket
        # FirmwareFetchError skip previously hid a dead stable-channel URL.
        pytest.skip(f"OTA server unreachable: {err}")
    assert version
