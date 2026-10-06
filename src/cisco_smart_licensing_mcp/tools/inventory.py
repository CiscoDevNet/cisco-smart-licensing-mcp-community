"""License inventory tools (Cisco Software APIs v1.0.2).

Read-only tools built on confirmed GET endpoints:

- ``sl_search_product_instances``     -> GET /licensing/v2/accounts/{sa}/devices
- ``sl_get_subscription_consumption`` -> GET /ea/v1/subscription/account/{sa}/consumption
- ``sl_get_license_summary``          -> POST /licensing/v2/get-summary (read-only query;
                                         POST only because the API takes a JSON body)

Plus a locked-down, GET-only, relative-path passthrough (``sl_get_license_inventory``)
for any other confirmed read-only endpoint in the spec without redeploying.

Security: the passthrough is GET-only, accepts a RELATIVE path only (no scheme
or host, so the client's SSRF host-allowlist still applies), and is read-only.
It is NOT a general-purpose HTTP client.
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..decorators import fail_soft
from ._common import (
    LimitParam,
    OffsetParam,
    SmartAccountDomain,
    VirtualAccountName,
    drop_none,
    extract_items,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ..registry import ServerContext

_DNA_A = re.compile(r"\bDNA[- ]?A(dvantage)?\b", re.I)
_DNA_E = re.compile(r"\bDNA[- ]?E(ssentials)?\b", re.I)


def _is_dna_a(feature: str) -> bool:
    return bool(_DNA_A.search(feature)) and "DNA" in feature.upper()


def _is_dna_e(feature: str) -> bool:
    return bool(_DNA_E.search(feature)) and "DNA" in feature.upper()


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
        name="sl_get_license_summary",
        description=(
            "Per-license summary for one Virtual Account, via POST "
            "/licensing/v2/get-summary (read-only query). Identify the account by "
            "'smart_account_domain' (exact match, resolved to its numeric ID) or "
            "'smart_account_id', and the VA by 'virtual_account_name' or "
            "'virtual_account_id'. Returns compact per-tag counts (license_details "
            "dropped) plus dna_advantage_in_use / dna_essentials_in_use and the tags "
            "that fed them. Network/Networkstack Advantage/Essentials are NOT DNA."
        ),
    )
    @soft
    def sl_get_license_summary(
        smart_account_domain: SmartAccountDomain | None = None,
        smart_account_id: Annotated[
            int | None, Field(default=None, ge=1, description="Numeric Smart Account ID.")
        ] = None,
        virtual_account_name: VirtualAccountName | None = None,
        virtual_account_id: Annotated[
            int | None, Field(default=None, ge=1, description="Numeric Virtual Account ID.")
        ] = None,
    ) -> dict[str, Any]:
        domain = smart_account_domain or ctx.settings.sl_smart_account_domain
        if smart_account_id is None:
            if not domain:
                return {
                    "status": "error",
                    "error": "Provide smart_account_id or smart_account_domain.",
                }
            found = ctx.client.get("/pnp/v2/accounts", params={"accountDomain": domain})
            exact = [
                a
                for a in extract_items(found)
                if isinstance(a, dict)
                and str(a.get("domainIdentifier", "")).lower() == domain.lower()
            ]
            if len(exact) != 1:
                return {
                    "status": "error",
                    "error": f"Domain {domain!r} matched {len(exact)} Smart Accounts exactly.",
                }
            smart_account_id = int(exact[0]["accountIdentifier"])
        if virtual_account_id is None:
            if not (virtual_account_name and domain):
                return {
                    "status": "error",
                    "error": "Provide virtual_account_id, or virtual_account_name plus a domain.",
                }
            listing = ctx.client.get(f"/pnp/v2/accounts/{domain}/virtual-accounts")
            matches = [
                v
                for v in extract_items(listing)
                if isinstance(v, dict) and v.get("virtualAccountName") == virtual_account_name
            ]
            if len(matches) != 1:
                return {
                    "status": "error",
                    "error": (
                        f"Virtual account {virtual_account_name!r} matched "
                        f"{len(matches)} entries in {domain}."
                    ),
                }
            virtual_account_id = int(matches[0]["virtualAccountId"])
        now_ms = int(time.time() * 1000)
        raw = ctx.client.post(
            "/licensing/v2/get-summary",
            json={"data": {"timestamp": now_ms, "nonce": str(now_ms)}},
            headers={
                "X-CSW-REQUESTING-SYSTEM": json.dumps({"display_name": "CSLU"}),
                "X-CSW-SMART-ACCOUNT-ID": str(smart_account_id),
                "X-CSW-VIRTUAL-ACCOUNT-ID": str(virtual_account_id),
            },
        )
        raw = raw if isinstance(raw, dict) else {}
        licenses = [
            {
                "display_name": s.get("display_name"),
                "entitled": s.get("entitled"),
                "inuse": s.get("inuse"),
                "reserved": s.get("reserved"),
                "compliance_status": s.get("compliance_status"),
            }
            for s in raw.get("summary") or []
            if isinstance(s, dict)
        ]
        dna_a = [x for x in licenses if _is_dna_a(x["display_name"] or "")]
        dna_e = [x for x in licenses if _is_dna_e(x["display_name"] or "")]
        return {
            "status": "ok",
            "smart_account_id": smart_account_id,
            "virtual_account_id": virtual_account_id,
            "api_status": raw.get("status"),
            "message": raw.get("message"),
            "outstanding_reports": raw.get("out_standing_reports"),
            "dna_advantage_in_use": sum(x["inuse"] or 0 for x in dna_a),
            "dna_essentials_in_use": sum(x["inuse"] or 0 for x in dna_e),
            "dna_advantage_tags": [(x["display_name"], x["inuse"]) for x in dna_a],
            "dna_essentials_tags": [(x["display_name"], x["inuse"]) for x in dna_e],
            "licenses": licenses,
        }

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
