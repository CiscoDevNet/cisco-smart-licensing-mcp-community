"""Thin REST client for the Cisco Smart Accounts & Licensing v2 API.

- All requests target the configured ``SL_BASE_URL`` host (SSRF-allowlisted).
- Injects ``Authorization: Bearer <token>`` from the Authenticator.
- Retries 429/5xx + transport errors within the retry budget.
- A single 401 triggers a token invalidation + one free re-auth attempt.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from .auth import Authenticator
from .errors import SLError, TransportError, status_to_error

logger = logging.getLogger(__name__)

JsonValue = Any
RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})


class SmartLicensingClient:
    """Synchronous client for the cloud CSSM Smart Licensing API."""

    def __init__(
        self,
        *,
        base_url: str,
        authenticator: Authenticator,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        user_agent: str = "cisco-smart-licensing-mcp/0.1",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = authenticator
        self._max_retries = max_retries
        self._user_agent = user_agent
        self._owned_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            verify=True,
            follow_redirects=False,
        )
        self._allowed_host = urlparse(self._base_url).hostname or ""

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> SmartLicensingClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> JsonValue:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        return self._request("POST", path, json_body=json, params=params, extra_headers=headers)

    # ------------------------------------------------------------------
    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self._base_url}{path}"
        if (urlparse(url).hostname or "") != self._allowed_host:
            raise SLError(f"Refusing to send request to unexpected host in path: {path!r}")
        return url

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "Authorization": f"Bearer {self._auth.get_token()}",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        url = self._build_url(path)
        max_attempts = max(1, self._max_retries + 1)
        token_retried = False
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers={**(extra_headers or {}), **self._headers()},
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "http transport error",
                    extra={"method": method, "path": path, "attempt": attempt, "error": str(exc)},
                )
                if attempt < max_attempts:
                    time.sleep(self._backoff(attempt))
                    continue
                raise TransportError(
                    f"HTTP transport error after {attempt} attempt(s): {exc!s}"
                ) from exc

            if response.status_code == 401 and not token_retried:
                logger.info("received 401, re-authenticating once", extra={"path": path})
                self._auth.invalidate()
                token_retried = True
                attempt -= 1
                continue

            if response.status_code in RETRYABLE_STATUSES and attempt < max_attempts:
                wait = self._retry_after(response) or self._backoff(attempt)
                logger.warning(
                    "retryable response",
                    extra={"path": path, "status": response.status_code, "wait": round(wait, 2)},
                )
                time.sleep(wait)
                continue

            return self._parse(response, method=method, path=path)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        ra = response.headers.get("Retry-After")
        if not ra:
            return None
        try:
            return max(0.0, float(ra))
        except ValueError:
            return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = 1.5 * (2 ** (attempt - 1))
        return min(30.0, base) + random.uniform(0, 0.25)  # noqa: S311 (jitter, not crypto)

    def _parse(self, response: httpx.Response, *, method: str, path: str) -> JsonValue:
        request_id = (
            response.headers.get("X-Request-Id")
            or response.headers.get("X-Correlation-Id")
        )
        if response.status_code == 204 or not response.content:
            if 200 <= response.status_code < 300:
                return None
            raise status_to_error(
                response.status_code,
                f"{method} {path} returned HTTP {response.status_code} (empty body)",
                request_id=request_id,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            if 200 <= response.status_code < 300:
                return {"_raw": response.text}
            raise status_to_error(
                response.status_code,
                f"{method} {path} returned HTTP {response.status_code} (non-JSON body)",
                request_id=request_id,
            ) from exc

        if 200 <= response.status_code < 300:
            return payload

        message = "HTTP " + str(response.status_code)
        if isinstance(payload, dict):
            message = (
                payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
                or message
            )
        raise status_to_error(
            response.status_code,
            f"{method} {path}: {message}",
            request_id=request_id,
            details=payload if isinstance(payload, dict) else {"body": payload},
        )
