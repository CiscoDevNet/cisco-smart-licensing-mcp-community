"""Smart Account / Virtual Account discovery (Cisco Software APIs v1.0.2).

Read-only tools built on confirmed GET endpoints:

- ``sl_list_smart_accounts``  -> GET /accounts/v1/user/search-smart-accounts
- ``sl_list_virtual_accounts`` -> GET /pnp/v2/accounts/{smartAccountDomain}/virtual-accounts

Use these first to find the exact Smart Account domain + Virtual Account name
that the inventory tools need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..decorators import fail_soft
from ._common import LimitParam, OffsetParam, SmartAccountDomain, drop_none

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ..registry import ServerContext

UserId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=256,
        description="CCO user id whose Smart Account roles to list.",
    ),
]


def register(mcp: FastMCP, ctx: ServerContext) -> None:
    soft = fail_soft(ctx)

    @mcp.tool(
        name="sl_list_smart_accounts",
        description=(
            "List the Smart Accounts (and, optionally, Virtual Accounts) that a CCO "
            "user has roles on, via GET /accounts/v1/user/search-smart-accounts. "
            "Read-only. Provide 'user_id' or set SL_USER_ID; set include_virtual_accounts "
            "to also return each account's Virtual Accounts in one call."
        ),
    )
    @soft
    def sl_list_smart_accounts(
        user_id: UserId | None = None,
        include_virtual_accounts: bool = True,
        smart_account_domain: SmartAccountDomain | None = None,
    ) -> dict[str, Any]:
        uid = user_id or ctx.settings.sl_user_id
        if not uid:
            return {
                "status": "error",
                "error": "user_id is required (pass it, or set SL_USER_ID in the environment).",
            }
        params = drop_none(
            {
                "userId": uid,
                "addVirtualAccounts": "true" if include_virtual_accounts else None,
                "addRoleDipslayName": "true",  # (sic) spelled this way in the Cisco spec
                "smartAccountDomain": smart_account_domain or ctx.settings.sl_smart_account_domain,
            }
        )
        result = ctx.client.get("/accounts/v1/user/search-smart-accounts", params=params)
        return {"status": "ok", "user_id": uid, "result": result}

    @mcp.tool(
        name="sl_list_virtual_accounts",
        description=(
            "List the Virtual Accounts under a Smart Account domain, via "
            "GET /pnp/v2/accounts/{smartAccountDomain}/virtual-accounts. Read-only. "
            "Omit 'smart_account_domain' to use SL_SMART_ACCOUNT_DOMAIN."
        ),
    )
    @soft
    def sl_list_virtual_accounts(
        smart_account_domain: SmartAccountDomain | None = None,
        rows_per_page: LimitParam = 50,
        start_index: OffsetParam = 0,
    ) -> dict[str, Any]:
        domain = smart_account_domain or ctx.settings.sl_smart_account_domain
        if not domain:
            return {
                "status": "error",
                "error": (
                    "smart_account_domain is required (pass it, or set "
                    "SL_SMART_ACCOUNT_DOMAIN in the environment)."
                ),
            }
        params = drop_none({"rowsPerPage": rows_per_page, "startIdx": start_index})
        result = ctx.client.get(f"/pnp/v2/accounts/{domain}/virtual-accounts", params=params)
        return {"status": "ok", "smart_account_domain": domain, "result": result}
