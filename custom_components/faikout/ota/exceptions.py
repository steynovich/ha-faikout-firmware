"""Exception hierarchy for the OTA core."""


class FaikoutError(Exception):
    """Base class for all Faikout OTA errors."""


class ManifestError(FaikoutError):
    """The OTA manifest was missing, malformed, or had no app entry."""


class FirmwareParseError(FaikoutError):
    """The firmware image did not contain a valid ESP-IDF app descriptor."""


class FirmwareFetchError(FaikoutError):
    """A network request to the OTA server failed."""
