"""Shared parameter primitives + response helpers for tool modules."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

# A Smart Account / Virtual Account domain or name. Cisco allows dots, dashes,
# underscores, spaces and @; keep it permissive but bounded.
SmartAccountDomain = Annotated[
    str,
    Field(
        min_length=1,
        max_length=256,
        description="Smart Account domain, e.g. 'example.cisco.com'.",
    ),
]
VirtualAccountName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=256,
        description="Virtual Account name as shown in CSSM.",
    ),
]
LimitParam = Annotated[
    int,
    Field(default=50, ge=1, le=500, description="Max records to return."),
]
OffsetParam = Annotated[
    int,
    Field(default=0, ge=0, le=1_000_000, description="Offset for pagination (0-based)."),
]


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip keys whose value is ``None`` so they don't end up in the query/body."""
    return {k: v for k, v in payload.items() if v is not None}


def extract_items(payload: Any) -> list[Any]:
    """Return the list-of-resources from a Smart Licensing list response.

    Common envelope shapes: a bare list, ``{"accounts": [...]}``,
    ``{"virtualAccounts": [...]}``, ``{"licenses": [...]}``, ``{"data": [...]}``.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("accounts", "virtualAccounts", "licenses", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []
