"""Tool discovery and registration.

Each ``tools/<resource>.py`` module defines a top-level:

    def register(mcp: FastMCP, ctx: ServerContext) -> None: ...

The registry imports the explicit module list (no disk auto-discovery, so the
tool catalog stays stable and reviewable) and calls each ``register`` only when
credentials are configured. With zero credentials the server boots clean and
exposes an empty tool list — handy for smoke-testing the binary.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .auth import Authenticator
from .client import SmartLicensingClient
from .config import Settings

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

TOOL_MODULES: list[str] = [
    "cisco_smart_licensing_mcp.tools.accounts",
    "cisco_smart_licensing_mcp.tools.inventory",
]


@dataclass
class ServerContext:
    settings: Settings
    auth: Authenticator
    client: SmartLicensingClient


def register_all(mcp: FastMCP, ctx: ServerContext) -> int:
    """Import and register every tool module. Returns the module count loaded."""
    if not ctx.auth.is_configured:
        logger.info(
            "no credentials configured; skipping tool registration",
            extra={"modules_skipped": len(TOOL_MODULES)},
        )
        return 0

    loaded = 0
    for dotted in TOOL_MODULES:
        module = importlib.import_module(dotted)
        register = getattr(module, "register", None)
        if not callable(register):
            raise RuntimeError(f"Tool module {dotted!r} is missing a register(mcp, ctx) function")
        register(mcp, ctx)
        loaded += 1
        logger.debug("registered tool module", extra={"module": dotted})

    logger.info(
        "tool registration complete",
        extra={"modules": loaded, "writes_enabled": ctx.settings.sl_enable_writes},
    )
    return loaded
