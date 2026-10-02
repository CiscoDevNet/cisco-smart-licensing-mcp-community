"""End-to-end tool tests against the real Software-APIs endpoints.

Mock strategy: POST is always the token endpoint; GET is always the API call
(so query strings don't have to be matched exactly). We assert on the captured
request URL to verify the tool hit the right path + params.
"""

from __future__ import annotations

from pytest_httpx import HTTPXMock

from cisco_smart_licensing_mcp.registry import ServerContext
from cisco_smart_licensing_mcp.tools import accounts, inventory

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"


def _token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json={"access_token": "t", "expires_in": 3599})


def _get(httpx_mock: HTTPXMock, payload) -> None:
    httpx_mock.add_response(method="GET", json=payload)


def test_list_smart_accounts_hits_search_endpoint(
    context: ServerContext, fake_mcp, httpx_mock: HTTPXMock
) -> None:
    _token(httpx_mock)
    _get(httpx_mock, {"accounts": [{"domain": "example.cisco.com"}]})
    accounts.register(fake_mcp, context)

    out = fake_mcp.tools["sl_list_smart_accounts"](user_id="testuser")
    assert out["status"] == "ok"
    assert out["user_id"] == "testuser"
    assert out["result"] == {"accounts": [{"domain": "example.cisco.com"}]}

    req = httpx_mock.get_request(method="GET")
    assert req is not None
    assert req.url.path == "/v1/software/apis/accounts/v1/user/search-smart-accounts"
    assert req.url.params["userId"] == "testuser"
    assert req.url.params["addVirtualAccounts"] == "true"


def test_list_smart_accounts_requires_user_id(
    context: ServerContext, fake_mcp, httpx_mock: HTTPXMock
) -> None:
    # No user_id passed and SL_USER_ID unset -> structured error, no HTTP call.
    accounts.register(fake_mcp, context)
    out = fake_mcp.tools["sl_list_smart_accounts"]()
    assert out["status"] == "error"
    assert "user_id" in out["error"]


def test_list_smart_accounts_uses_default_user_id(
    context: ServerContext, fake_mcp, httpx_mock: HTTPXMock, monkeypatch
) -> None:
    monkeypatch.setattr(context.settings, "sl_user_id", "default-cco")
    _token(httpx_mock)
    _get(httpx_mock, {"accounts": []})
    accounts.register(fake_mcp, context)

    out = fake_mcp.tools["sl_list_smart_accounts"]()
    assert out["user_id"] == "default-cco"
    assert httpx_mock.get_request(method="GET").url.params["userId"] == "default-cco"


def test_list_virtual_accounts(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    _get(httpx_mock, {"virtualAccounts": [{"name": "DEFAULT"}]})
    accounts.register(fake_mcp, context)

    out = fake_mcp.tools["sl_list_virtual_accounts"](smart_account_domain="example.cisco.com")
    assert out["status"] == "ok"
    assert out["smart_account_domain"] == "example.cisco.com"
    req = httpx_mock.get_request(method="GET")
    assert req.url.path == "/v1/software/apis/pnp/v2/accounts/example.cisco.com/virtual-accounts"


def test_list_virtual_accounts_requires_domain(
    context: ServerContext, fake_mcp, httpx_mock: HTTPXMock
) -> None:
    accounts.register(fake_mcp, context)
    out = fake_mcp.tools["sl_list_virtual_accounts"]()
    assert out["status"] == "error"
    assert "smart_account_domain" in out["error"]


def test_search_product_instances(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    _get(httpx_mock, {"devices": [{"instanceName": "rtr1"}]})
    inventory.register(fake_mcp, context)

    out = fake_mcp.tools["sl_search_product_instances"](
        virtual_account_name="DEFAULT", smart_account_domain="example.cisco.com"
    )
    assert out["status"] == "ok"
    req = httpx_mock.get_request(method="GET")
    assert req.url.path == "/v1/software/apis/licensing/v2/accounts/example.cisco.com/devices"
    assert req.url.params["virtualAccountName"] == "DEFAULT"


def test_subscription_consumption(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    _get(httpx_mock, {"consumption": []})
    inventory.register(fake_mcp, context)

    out = fake_mcp.tools["sl_get_subscription_consumption"](smart_account_domain="example.cisco.com")
    assert out["status"] == "ok"
    req = httpx_mock.get_request(method="GET")
    assert req.url.path == "/v1/software/apis/ea/v1/subscription/account/example.cisco.com/consumption"


def test_fail_soft_denied_on_403(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    httpx_mock.add_response(method="GET", status_code=403, json={"message": "no access"})
    accounts.register(fake_mcp, context)

    out = fake_mcp.tools["sl_list_smart_accounts"](user_id="testuser")
    assert out["status"] == "denied"
    assert out["status_code"] == 403


def test_fail_soft_unreachable_on_503(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    for _ in range(context.settings.http_max_retries + 1):
        httpx_mock.add_response(method="GET", status_code=503)
    accounts.register(fake_mcp, context)

    out = fake_mcp.tools["sl_list_smart_accounts"](user_id="testuser")
    assert out["status"] == "unreachable"


def test_inventory_passthrough_get(context: ServerContext, fake_mcp, httpx_mock: HTTPXMock) -> None:
    _token(httpx_mock)
    _get(httpx_mock, {"policy": {"topic": "x"}})
    inventory.register(fake_mcp, context)

    out = fake_mcp.tools["sl_get_license_inventory"](path="/licensing/v2/account-policy")
    assert out["status"] == "ok"
    assert out["result"] == {"policy": {"topic": "x"}}
    req = httpx_mock.get_request(method="GET")
    assert req.url.path == "/v1/software/apis/licensing/v2/account-policy"
