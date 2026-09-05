from urllib.parse import urlparse

from custom_components.faikout.const import (
    DOMAIN,
    MANIFEST_URLS,
    Channel,
    manifest_url_for,
)
from custom_components.faikout.ota.exceptions import (
    FaikoutError,
    FirmwareFetchError,
    FirmwareParseError,
    ManifestError,
)


def test_domain():
    assert DOMAIN == "faikout"


def test_channel_values():
    assert Channel.STABLE == "stable"
    assert Channel.BETA == "beta"


def test_manifest_url_for_known_target():
    assert manifest_url_for("Faikout-S3-MINI-N4-R2", Channel.STABLE) == (
        "https://ota.faikout.uk/Faikout.manifest"
    )
    assert manifest_url_for("Faikout-S3-MINI-N4-R2", Channel.BETA) == (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    )


def test_manifest_url_for_unknown_target_returns_none():
    assert manifest_url_for("Nope-X1", Channel.BETA) is None


def test_every_channel_has_at_least_one_target():
    # FaikoutCoordinator raises UpdateFailed with no underlying error if a channel
    # resolves to zero manifest URLs, so every Channel member must be represented.
    for channel in Channel:
        assert any(c is channel for _, c in MANIFEST_URLS), f"no manifest URL for {channel}"


def test_manifest_urls_are_https_on_the_ota_host():
    for url in MANIFEST_URLS.values():
        parsed = urlparse(url)
        assert parsed.scheme == "https", url
        assert parsed.netloc == "ota.faikout.uk", url


def test_exception_hierarchy():
    for exc in (ManifestError, FirmwareParseError, FirmwareFetchError):
        assert issubclass(exc, FaikoutError)
