"""Exception hierarchy for the OTA core."""


class FaikoutError(Exception):
    """Base class for all Faikout OTA errors."""


class ManifestError(FaikoutError):
    """The OTA manifest was missing, malformed, or had no app entry."""


class FirmwareParseError(FaikoutError):
    """The firmware image did not contain a valid ESP-IDF app descriptor."""


class FirmwareFetchError(FaikoutError):
    """A network request to the OTA server failed."""


class FirmwareUnavailableError(FirmwareFetchError):
    """The OTA server could not be reached at all (connection refused, timeout).

    Distinct from a plain FirmwareFetchError, which also covers a server that
    answered with an error status: a 404 is a broken URL worth failing on, while
    an unreachable host is an environment problem worth skipping or retrying.
    """
