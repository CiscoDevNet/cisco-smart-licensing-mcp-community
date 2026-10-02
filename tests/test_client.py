"""REST client: bearer injection, 401 re-auth, retries, SSRF guard."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from cisco_smart_licensing_mcp.errors import NotFoundError
from cisco_smart_licensing_mcp.registry import ServerContext

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
SEARCH_URL = "https://apx.cisco.com/v1/software/apis/pnp/v2/accounts"


def test_get_injects_bearer_token(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "tok", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", json={"accounts": []})

    result = context.client.get("/pnp/v2/accounts")
    assert result == {"accounts": []}

    api_req = httpx_mock.get_request(url=SEARCH_URL)
    assert api_req is not None
    assert api_req.headers["Authorization"] == "Bearer tok"


def test_401_triggers_single_reauth(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    # First token, then a 401 on the API, then a fresh token + success.
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "old", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", status_code=401, json={"error": "expired"})
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "new", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", json={"accounts": [{"domain": "x"}]})

    result = context.client.get("/pnp/v2/accounts")
    assert result == {"accounts": [{"domain": "x"}]}
    # Two token fetches (initial + after invalidate) and two API calls.
    assert len(httpx_mock.get_requests(url=TOKEN_URL)) == 2
    assert len(httpx_mock.get_requests(url=SEARCH_URL)) == 2


def test_retries_on_503_then_succeeds(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", status_code=503)
    httpx_mock.add_response(url=SEARCH_URL, method="GET", json={"accounts": []})

    result = context.client.get("/pnp/v2/accounts")
    assert result == {"accounts": []}
    assert len(httpx_mock.get_requests(url=SEARCH_URL)) == 2


def test_404_raises_notfound(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", status_code=404, json={"message": "nope"})
    with pytest.raises(NotFoundError):
        context.client.get("/pnp/v2/accounts")


def test_empty_204_body_returns_none(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 3599})
    httpx_mock.add_response(url=SEARCH_URL, method="GET", status_code=204)
    assert context.client.get("/pnp/v2/accounts") is None


def test_non_json_2xx_wrapped_as_raw(context: ServerContext, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 3599})
    httpx_mock.add_response(
        url=SEARCH_URL, method="GET", status_code=200, text="just text", headers={"Content-Type": "text/plain"}
    )
    assert context.client.get("/pnp/v2/accounts") == {"_raw": "just text"}
