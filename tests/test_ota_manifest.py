import json

import pytest

from custom_components.faikout.ota.exceptions import ManifestError
from custom_components.faikout.ota.manifest import parse_manifest

VALID = {
    "flash": [
        {"url": "https://ota.faikout.uk/boot.bin"},
        {"address": "8000", "url": "https://ota.faikout.uk/part.bin"},
        {"address": "10000", "url": "https://ota.faikout.uk/app.bin", "app": True},
    ]
}


def test_returns_app_url_from_dict():
    assert parse_manifest(VALID) == "https://ota.faikout.uk/app.bin"


def test_returns_app_url_from_bytes():
    assert parse_manifest(json.dumps(VALID).encode()) == "https://ota.faikout.uk/app.bin"


def test_invalid_json_raises():
    with pytest.raises(ManifestError):
        parse_manifest(b"not json{")


def test_no_app_entry_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"flash": [{"url": "https://ota.faikout.uk/boot.bin"}]})


def test_missing_flash_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "Faikout"})


def test_app_entry_without_url_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"flash": [{"address": "10000", "app": True}]})
