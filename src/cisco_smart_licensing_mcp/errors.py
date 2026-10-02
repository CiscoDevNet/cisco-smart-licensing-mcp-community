"""Exception types for cisco-smart-licensing-mcp.

Designed to surface clean, redacted, actionable messages to the MCP client
without leaking secrets or stack traces. ``@fail_soft`` maps a subset of these
to structured envelopes so a playbook can iterate over tools without crashing
on transient network/auth failures.
"""

from __future__ import annotations


class SLError(Exception):
    """Base class for all errors raised by this server."""


class ConfigurationError(SLError):
    """Required configuration is missing or invalid."""


class CredentialsNotConfiguredError(ConfigurationError):
    """A tool was invoked that needs client credentials we don't have."""


class AuthenticationError(SLError):
    """Token endpoint returned an error, or returned a malformed token."""


class SLAPIError(SLError):
    """A non-2xx response from the Smart Licensing API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.details = details or {}


class RateLimitedError(SLAPIError):
    """The API returned 429 after retries were exhausted."""


class NotFoundError(SLAPIError):
    """The requested resource doesn't exist (404)."""


class ValidationError(SLAPIError):
    """The API rejected the request as malformed (400)."""


class ForbiddenError(SLAPIError):
    """The API rejected the request as unauthorized (401/403)."""


class ServerError(SLAPIError):
    """The API returned a 5xx after retries were exhausted."""


class TransportError(SLAPIError):
    """No response was obtained (DNS/TLS/timeout/connection)."""


def status_to_error(
    status_code: int,
    message: str,
    *,
    request_id: str | None = None,
    details: dict | None = None,
) -> SLAPIError:
    """Map an HTTP status code to a richer error subtype."""
    cls: type[SLAPIError]
    if status_code == 400:
        cls = ValidationError
    elif status_code in (401, 403):
        cls = ForbiddenError
    elif status_code == 404:
        cls = NotFoundError
    elif status_code == 429:
        cls = RateLimitedError
    elif 500 <= status_code < 600:
        cls = ServerError
    else:
        cls = SLAPIError
    return cls(message, status_code=status_code, request_id=request_id, details=details)
