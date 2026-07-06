from custom_components.faikout.const import (
    DOMAIN,
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
        "https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json"
    )
    assert manifest_url_for("Faikout-S3-MINI-N4-R2", Channel.BETA) == (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    )


def test_manifest_url_for_unknown_target_returns_none():
    assert manifest_url_for("Nope-X1", Channel.BETA) is None


def test_exception_hierarchy():
    for exc in (ManifestError, FirmwareParseError, FirmwareFetchError):
        assert issubclass(exc, FaikoutError)
