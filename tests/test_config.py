"""Settings validation: defaults, credential pairing, URL + SSRF guards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cisco_smart_licensing_mcp.config import load_settings


def test_defaults_with_no_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    s = load_settings()
    assert s.has_credentials is False
    assert s.sl_token_url == "https://id.cisco.com/oauth2/default/v1/token"
    assert s.sl_base_url == "https://apx.cisco.com/v1/software/apis"
    assert s.mcp_transport == "stdio"
    assert s.sl_enable_writes is False


def test_credentials_must_be_paired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_CLIENT_ID", "only-id")
    with pytest.raises(ValidationError):
        load_settings()


def test_full_credentials_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_CLIENT_ID", "id")
    monkeypatch.setenv("SL_CLIENT_SECRET", "secret")
    s = load_settings()
    assert s.has_credentials is True
    # SecretStr never renders the raw value in repr/str
    assert "secret" not in repr(s.sl_client_secret)


def test_non_https_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_BASE_URL", "http://swapi.cisco.com/x")
    with pytest.raises(ValidationError):
        load_settings()


def test_ssrf_host_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_CLIENT_ID", "id")
    monkeypatch.setenv("SL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SL_BASE_URL", "https://evil.example.com/api")
    with pytest.raises(ValidationError):
        load_settings()


def test_ssrf_override_allows_custom_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_BASE_URL", "https://internal.example.com/api")
    monkeypatch.setenv("SL_ALLOW_CUSTOM_HOST", "true")
    s = load_settings()
    assert s.sl_base_url == "https://internal.example.com/api"


def test_trailing_slash_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SL_BASE_URL", "https://swapi.cisco.com/x/")
    s = load_settings()
    assert s.sl_base_url == "https://swapi.cisco.com/x"
