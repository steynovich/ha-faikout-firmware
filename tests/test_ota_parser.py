import struct

import pytest

from custom_components.faikout.ota.exceptions import FirmwareParseError
from custom_components.faikout.ota.parser import parse_app_descriptor

MAGIC = 0xABCD5432


def _descriptor(version="1a347969"):
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += version.encode("ascii").ljust(32, b"\x00")   # version[32]
    body += b"Faikout".ljust(32, b"\x00")                # project_name[32]
    return body


def test_parses_version_at_offset_zero():
    assert parse_app_descriptor(_descriptor()) == "1a347969"


def test_finds_descriptor_after_image_header():
    head = b"\xe9\x07\x02\x20" + b"\x11" * 28 + _descriptor()
    assert parse_app_descriptor(head) == "1a347969"


def test_missing_magic_raises():
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(b"\x00" * 512)


def test_truncated_after_magic_raises():
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(_descriptor()[:30])
