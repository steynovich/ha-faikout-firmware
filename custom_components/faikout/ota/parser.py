"""Extract the version string from an ESP-IDF esp_app_desc_t struct."""

from __future__ import annotations

import struct

from .exceptions import FirmwareParseError

_MAGIC_BYTES = struct.pack("<I", 0xABCD5432)  # b"\x52\x54\xcd\xab"
_VERSION_OFF = 16
_VERSION_LEN = 32


def parse_app_descriptor(head: bytes) -> str:
    """Return the firmware version located via the app descriptor magic word."""
    base = head.find(_MAGIC_BYTES)
    if base == -1:
        raise FirmwareParseError("app descriptor magic word 0xABCD5432 not found")
    start = base + _VERSION_OFF
    end = start + _VERSION_LEN
    if len(head) < end:
        raise FirmwareParseError("firmware head truncated before version field")
    raw = head[start:end]
    version = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if not version:
        raise FirmwareParseError("app descriptor version field is empty")
    return version
