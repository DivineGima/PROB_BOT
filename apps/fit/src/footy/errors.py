"""Exit codes and the exceptions that map to them (architecture section 6.7).

Messages never contain tokens, request headers or response bodies.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    UNEXPECTED = 1
    DATA = 2
    SOURCE_OUTAGE = 3
    FIT = 4


class FootyError(Exception):
    """Base class for expected failures."""

    exit_code = ExitCode.UNEXPECTED


class ConfigError(FootyError):
    """A required setting is missing or the source is not enabled (legal gate)."""

    exit_code = ExitCode.DATA


class DataError(FootyError):
    """Source data or local data files failed validation, or sources disagree."""

    exit_code = ExitCode.DATA


class SourceOutage(FootyError):
    """The source could not be reached after bounded retries (FR-17: continue with stored data)."""

    exit_code = ExitCode.SOURCE_OUTAGE


class SourceRestricted(FootyError):
    """The source answered but the free plan does not allow this resource (HTTP 403)."""

    exit_code = ExitCode.DATA


class SourceAuthError(FootyError):
    """The token was rejected (HTTP 401). Not retried."""

    exit_code = ExitCode.DATA
