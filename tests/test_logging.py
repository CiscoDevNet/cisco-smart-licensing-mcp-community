"""Secret redaction in structured logs / evidence payloads."""

from __future__ import annotations

from cisco_smart_licensing_mcp.logging import REDACTED, redact


def test_sensitive_field_names_redacted() -> None:
    out = redact(
        {
            "client_secret": "super-secret",
            "access_token": "tok",
            "authorization": "Bearer xyz",
            "domain": "acme.example.com",
        }
    )
    assert out["client_secret"] == REDACTED
    assert out["access_token"] == REDACTED
    assert out["authorization"] == REDACTED
    assert out["domain"] == "acme.example.com"  # non-sensitive passes through


def test_bearer_and_jwt_scrubbed_from_free_text() -> None:
    out = redact({"msg": "called with Authorization: Bearer eyJabc.def.ghi to fetch"})
    assert "eyJabc.def.ghi" not in out["msg"]
    assert REDACTED in out["msg"]


def test_nested_structures_redacted() -> None:
    out = redact({"outer": {"client_id": "cid", "list": [{"secret": "s"}]}})
    assert out["outer"]["client_id"] == REDACTED
    assert out["outer"]["list"][0]["secret"] == REDACTED
