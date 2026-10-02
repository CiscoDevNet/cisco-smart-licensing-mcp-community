"""Shared test fixtures.

Keeps every test hermetic: no ``SL_*`` variable from the developer's real shell
leaks into a test, and helpers build a ready-to-use client/context wired to the
``pytest-httpx`` mock transport.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from cisco_smart_licensing_mcp.auth import build_authenticator
from cisco_smart_licensing_mcp.client import SmartLicensingClient
from cisco_smart_licensing_mcp.config import Settings, load_settings
from cisco_smart_licensing_mcp.registry import ServerContext

TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
API_BASE = "https://apx.cisco.com/v1/software/apis"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any real SL_* / MCP_* env so tests don't inherit developer creds."""
    import os

    for key in list(os.environ):
        if key.startswith(("SL_", "MCP_", "HTTP_", "LOG_")):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("SL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("SL_CLIENT_SECRET", "test-client-secret")
    # tight refresh skew so token-expiry tests are quick to reason about
    monkeypatch.setenv("SL_TOKEN_REFRESH_SKEW_SECONDS", "10")
    monkeypatch.setenv("HTTP_MAX_RETRIES", "2")
    return load_settings()


@pytest.fixture
def context(settings: Settings) -> ServerContext:
    auth = build_authenticator(settings)
    client = SmartLicensingClient(
        base_url=settings.sl_base_url,
        authenticator=auth,
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
    )
    return ServerContext(settings=settings, auth=auth, client=client)


class FakeMCP:
    """Minimal stand-in for FastMCP that records decorated tool callables.

    ``register(mcp, ctx)`` calls ``mcp.tool(name=..., description=...)(fn)``; we
    capture ``fn`` so tests can invoke the *real* (fail-soft-wrapped) tool logic
    directly, independent of the installed FastMCP version.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}
        self.descriptions: dict[str, str] = {}

    def tool(self, *, name: str, description: str = "") -> Callable[..., Any]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = fn
            self.descriptions[name] = description
            return fn

        return decorator


@pytest.fixture
def fake_mcp() -> FakeMCP:
    return FakeMCP()
