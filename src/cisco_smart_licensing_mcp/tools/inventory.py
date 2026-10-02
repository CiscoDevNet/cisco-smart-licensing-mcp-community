"""License inventory tools (Cisco Software APIs v1.0.2).

Read-only tools built on confirmed GET endpoints:

- ``sl_search_product_instances``     -> GET /licensing/v2/accounts/{sa}/devices
- ``sl_get_subscription_consumption`` -> GET /ea/v1/subscription/account/{sa}/consumption

Plus a locked-down, GET-only, relative-path passthrough (``sl_get_license_inventory``)
for any other confirmed read-only endpoint in the spec without redeploying.

Security: the passthrough is GET-only, accepts a RELATIVE path only (no scheme
or host, so the client's SSRF host-allowlist still applies), and is read-only.
It is NOT a general-purpose HTTP client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..decorators import fail_soft
from ._common import LimitParam, OffsetParam, SmartAccountDomain, VirtualAccountName, drop_none

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ..registry import ServerContext

RelativeApiPath = Annotated[
    str,
    Field(
        min_length=1,
        max_length=1024,
        pattern=r"^/[A-Za-z0-9._~%\-/]*$",
        description=(
            "Relative Software-APIs path, e.g. '/pnp/v2/accounts' or "
            "'/licensing/v2/accounts/{domain}/devices'. Must start with '/'. "
            "No scheme, host, or query string (use 'params' for query args)."
        ),
    ),
]


def register(mcp: FastMCP, ctx: ServerContext) -> None:
    soft = fail_soft(ctx)

    @mcp.tool(
        name="sl_search_product_instances",
        description=(
            "Search product instances (devices consuming licenses) in a Virtual "
            "Account, via GET /licensing/v2/accounts/{smartAccountDomain}/devices. "
            "Read-only. 'virtual_account_name' is required; 'smart_account_domain' "
            "falls back to SL_SMART_ACCOUNT_DOMAIN."
        ),
    )
    @soft
    def sl_search_product_instances(
        virtual_account_name: VirtualAccountName,
        smart_account_domain: SmartAccountDomain | None = None,
        instance_name: Annotated[
            str | None,
            Field(
                default=None,
                max_length=256,
                description="Filter by product instance / display name.",
            ),
        ] = None,
        limit: LimitParam = 50,
        offset: OffsetParam = 0,
    ) -> dict[str, Any]:
        domain = smart_account_domain or ctx.settings.sl_smart_account_domain
        if not domain:
            return {
                "status": "error",
                "error": "smart_account_domain is required (or set SL_SMART_ACCOUNT_DOMAIN).",
            }
        params = drop_none(
            {
                "virtualAccountName": virtual_account_name,
                "instanceName": instance_name,
                "limit": limit,
                "offset": offset,
            }
        )
        result = ctx.client.get(f"/licensing/v2/accounts/{domain}/devices", params=params)
        return {
            "status": "ok",
            "smart_account_domain": domain,
            "virtual_account_name": virtual_account_name,
            "result": result,
        }

    @mcp.tool(
        name="sl_get_subscription_consumption",
        description=(
            "Get the Smart Account consumption report across all EA subscriptions, "
            "via GET /ea/v1/subscription/account/{smartAccountDomain}/consumption. "
            "Read-only. 'smart_account_domain' falls back to SL_SMART_ACCOUNT_DOMAIN."
        ),
    )
    @soft
    def sl_get_subscription_consumption(
        smart_account_domain: SmartAccountDomain | None = None,
    ) -> dict[str, Any]:
        domain = smart_account_domain or ctx.settings.sl_smart_account_domain
        if not domain:
            return {
                "status": "error",
                "error": "smart_account_domain is required (or set SL_SMART_ACCOUNT_DOMAIN).",
            }
        result = ctx.client.get(f"/ea/v1/subscription/account/{domain}/consumption")
        return {"status": "ok", "smart_account_domain": domain, "result": result}

    @mcp.tool(
        name="sl_get_license_inventory",
        description=(
            "Read-only GET against any confirmed Software-APIs path (relative to the "
            "configured base URL). Escape hatch for endpoints not yet promoted to "
            "first-class tools. Example: '/licensing/v2/account-policy'."
        ),
    )
    @soft
    def sl_get_license_inventory(
        path: RelativeApiPath,
        params: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Optional query parameters as a flat object."),
        ] = None,
    ) -> dict[str, Any]:
        result = ctx.client.get(path, params=params)
        return drop_none({"status": "ok", "path": path, "result": result})
