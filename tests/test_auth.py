"""OAuth2 client-credentials token provider behaviour."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr
from pytest_httpx import HTTPXMock

from cisco_smart_licensing_mcp.auth import ClientCredentialsTokenProvider
from cisco_smart_licensing_mcp.errors import AuthenticationError

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"


def _provider(skew: int = 10) -> ClientCredentialsTokenProvider:
    return ClientCredentialsTokenProvider(
        token_url=TOKEN_URL,
        client_id="cid",
        client_secret=SecretStr("shh-secret"),
        refresh_skew_seconds=skew,
        http_client=httpx.Client(),
    )


def test_fetches_and_caches_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "abc123", "expires_in": 3599, "token_type": "Bearer"},
    )
    p = _provider()
    assert p.get_token() == "abc123"
    # Second call must be served from cache -> still only one HTTP request.
    assert p.get_token() == "abc123"
    assert len(httpx_mock.get_requests(url=TOKEN_URL)) == 1


def test_sends_client_credentials_grant(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 60})
    _provider().get_token()
    req = httpx_mock.get_request(url=TOKEN_URL)
    assert req is not None
    body = req.content.decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=cid" in body
    assert req.headers["Content-Type"].startswith("application/x-www-form-urlencoded")


def test_expired_token_triggers_refetch(httpx_mock: HTTPXMock) -> None:
    # expires_in less than the skew -> considered expired immediately -> refetch each call
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "a", "expires_in": 1})
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "b", "expires_in": 1})
    p = _provider(skew=10)
    assert p.get_token() == "a"
    assert p.get_token() == "b"
    assert len(httpx_mock.get_requests(url=TOKEN_URL)) == 2


def test_invalidate_forces_refetch(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "a", "expires_in": 3599})
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "b", "expires_in": 3599})
    p = _provider()
    assert p.get_token() == "a"
    p.invalidate()
    assert p.get_token() == "b"


def test_non_200_raises_without_leaking_secret(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", status_code=401, json={"error": "invalid_client"})
    p = _provider()
    with pytest.raises(AuthenticationError) as exc:
        p.get_token()
    msg = str(exc.value)
    assert "401" in msg
    assert "shh-secret" not in msg  # secret must never appear in the error


def test_malformed_response_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"no_token_here": True})
    with pytest.raises(AuthenticationError):
        _provider().get_token()
