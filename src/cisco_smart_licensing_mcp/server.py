"""FastMCP entrypoint for cisco-smart-licensing-mcp.

Default transport is **stdio** (per codeguard-0-mcp-security). HTTP transport is
opt-in via ``MCP_TRANSPORT=http`` and should only bind to 127.0.0.1.

Boot: parse env -> configure logging -> build Authenticator + client -> register
tools (only when creds present) -> run. Zero-cred boot yields an empty catalog.
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import __version__
from .auth import build_authenticator
from .client import SmartLicensingClient
from .config import Settings, load_settings
from .errors import ConfigurationError
from .logging import configure_logging
from .registry import ServerContext, register_all

logger = logging.getLogger(__name__)


def build_server(settings: Settings) -> tuple[FastMCP, ServerContext]:
    mcp = FastMCP(
        "cisco-smart-licensing",
        instructions=(
            "Read-only tools for Cisco cloud Smart Software Manager (CSSM) license "
            "inventory: Smart Accounts, Virtual Accounts, and their license "
            "entitlements. Authenticates machine-to-machine via OAuth2 "
            "client-credentials (no Cisco SSO in the request path). All "
            "credentials come from environment variables on the server side."
        ),
    )
    auth = build_authenticator(settings)
    client = SmartLicensingClient(
        base_url=settings.sl_base_url,
        authenticator=auth,
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
        user_agent=f"cisco-smart-licensing-mcp/{__version__}",
    )
    ctx = ServerContext(settings=settings, auth=auth, client=client)
    modules = register_all(mcp, ctx)
    logger.info("boot complete", extra={"version": __version__, "modules": modules})
    return mcp, ctx


def main() -> int:
    try:
        settings = load_settings()
    except Exception as exc:
        sys.stderr.write(
            f"cisco-smart-licensing-mcp: configuration error: {exc}\n"
            "See .env.example / ACCESS_GUIDE.md for the required environment variables.\n"
        )
        return 2

    configure_logging(settings.log_level)
    logger.info(
        "starting cisco-smart-licensing-mcp",
        extra={
            "version": __version__,
            "transport": settings.mcp_transport,
            "writes_enabled": settings.sl_enable_writes,
            "credentials_configured": settings.has_credentials,
        },
    )

    try:
        mcp, _ctx = build_server(settings)
    except ConfigurationError as exc:
        logger.error("configuration error: %s", exc)
        return 2

    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
    elif settings.mcp_transport == "http":
        mcp.settings.host = settings.mcp_http_host
        mcp.settings.port = settings.mcp_http_port
        logger.warning(
            "starting HTTP transport (trusted local dev only; bind 127.0.0.1)",
            extra={"host": settings.mcp_http_host, "port": settings.mcp_http_port},
        )
        mcp.run(transport="streamable-http")
    else:
        logger.error("unknown transport: %s", settings.mcp_transport)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
