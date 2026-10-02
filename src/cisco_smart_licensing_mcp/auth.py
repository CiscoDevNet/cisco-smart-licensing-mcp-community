"""OAuth 2.0 client-credentials token provider for cloud CSSM.

Flow:
    POST {token_url}
      Content-Type: application/x-www-form-urlencoded
      body: grant_type=client_credentials
            client_id=<...>
            client_secret=<...>
    -> {"access_token": "...", "token_type": "Bearer", "expires_in": 3599, ...}

The access token is cached in memory and proactively refreshed a configurable
number of seconds before expiry. The client_secret is held as a ``SecretStr``
and never logged. A 401 from the API triggers ``invalidate()`` + one re-auth.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import httpx
from pydantic import SecretStr

from .errors import AuthenticationError, CredentialsNotConfiguredError

logger = logging.getLogger(__name__)


@dataclass
class _CachedToken:
    access_token: str
    expires_at_monotonic: float

    def is_expired(self, *, now: float, skew: float) -> bool:
        return now >= (self.expires_at_monotonic - skew)


class ClientCredentialsTokenProvider:
    """Fetches + caches a Bearer token via the client-credentials grant."""

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: SecretStr,
        refresh_skew_seconds: int,
        http_client: httpx.Client,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_skew = refresh_skew_seconds
        self._client = http_client
        self._lock = threading.Lock()
        self._cached: _CachedToken | None = None

    def get_token(self) -> str:
        now = time.monotonic()
        cached = self._cached
        if cached is not None and not cached.is_expired(now=now, skew=self._refresh_skew):
            return cached.access_token
        with self._lock:
            now = time.monotonic()
            cached = self._cached
            if cached is not None and not cached.is_expired(now=now, skew=self._refresh_skew):
                return cached.access_token
            self._cached = self._fetch()
            return self._cached.access_token

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    # ------------------------------------------------------------------
    def _fetch(self) -> _CachedToken:
        logger.debug("fetching client-credentials token", extra={"endpoint": self._token_url})
        try:
            response = self._client.post(
                self._token_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret.get_secret_value(),
                },
            )
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Failed to reach token endpoint: {exc!s}") from exc

        if response.status_code != 200:
            # Do NOT echo the body verbatim — it may reflect the client_secret.
            try:
                err = response.json().get("error", "unknown_error")
            except ValueError:
                err = "non_json_error"
            raise AuthenticationError(
                f"Token endpoint returned HTTP {response.status_code} ({err}). "
                "If you just registered the app, allow ~30 min for the client to "
                "propagate; until then 401s are expected."
            )

        try:
            payload = response.json()
            access_token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3599))
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthenticationError("Token endpoint returned a malformed response") from exc

        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationError("Token endpoint returned an empty access_token")

        expires_at = time.monotonic() + max(0, expires_in)
        logger.info("obtained access token", extra={"expires_in_seconds": expires_in})
        return _CachedToken(access_token=access_token, expires_at_monotonic=expires_at)


@dataclass
class Authenticator:
    """Holds the single token provider (or None when creds aren't configured)."""

    provider: ClientCredentialsTokenProvider | None = None

    @property
    def is_configured(self) -> bool:
        return self.provider is not None

    def get_token(self) -> str:
        if self.provider is None:
            raise CredentialsNotConfiguredError(
                "No credentials configured. Set SL_CLIENT_ID and SL_CLIENT_SECRET "
                "(see ACCESS_GUIDE.md)."
            )
        return self.provider.get_token()

    def invalidate(self) -> None:
        if self.provider is not None:
            self.provider.invalidate()


def build_authenticator(
    settings,
    *,
    http_client: httpx.Client | None = None,
) -> Authenticator:
    """Construct the Authenticator from current settings."""
    if not settings.has_credentials:
        return Authenticator(provider=None)

    if http_client is None:
        http_client = httpx.Client(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            verify=True,
            follow_redirects=False,
        )
    provider = ClientCredentialsTokenProvider(
        token_url=settings.sl_token_url,
        client_id=settings.sl_client_id,
        client_secret=settings.sl_client_secret,
        refresh_skew_seconds=settings.sl_token_refresh_skew_seconds,
        http_client=http_client,
    )
    return Authenticator(provider=provider)
