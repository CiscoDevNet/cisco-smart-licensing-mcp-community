"""Configuration for cisco-smart-licensing-mcp.

All configuration comes from environment variables. Credentials are NEVER read
from CLI flags or committed config files (see codeguard-1-hardcoded-credentials).

Cloud CSSM auth model (machine-to-machine):

1. POST client_id + client_secret (grant_type=client_credentials) to Cisco's
   OAuth token endpoint  ->  short-lived Bearer access token.
2. Call the Cisco "Software APIs" on ``apx.cisco.com`` with
   ``Authorization: Bearer <token>``.

No human SSO / SAML / MFA is involved — that's the whole point of using the
API Console client-credentials grant instead of scraping the web UI.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TransportName = Literal["stdio", "http"]

# Cisco's OAuth token endpoint. Newly registered API Console (client-credentials)
# apps use id.cisco.com; the legacy cloudsso.cisco.com/as/token.oauth2 endpoint
# still issues tokens for older clients. Override via SL_TOKEN_URL if needed.
# NOTE: this is a public OAuth *endpoint URL*, not a credential (S105 false positive).
DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"  # noqa: S105

# Cisco "Software APIs" base (cloud CSSM). Confirmed from the official OpenAPI
# spec (software_ap_is 1.0.2): servers[0].url = https://apx.cisco.com/v1/software/apis
DEFAULT_API_BASE_URL = "https://apx.cisco.com/v1/software/apis"

# SSRF defense: outbound hosts must end with one of these suffixes.
TRUSTED_HOST_SUFFIXES: tuple[str, ...] = (".cisco.com",)


class Settings(BaseSettings):
    """Server settings sourced exclusively from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=None,  # the wrapper script sources .env into the process env
        case_sensitive=False,
        extra="ignore",
    )

    # === OAuth2 client-credentials =======================================
    sl_client_id: str | None = Field(
        default=None,
        description="OAuth2 client_id from the Cisco API Console app registration.",
        max_length=256,
    )
    sl_client_secret: SecretStr | None = Field(
        default=None,
        description="OAuth2 client_secret from the Cisco API Console app registration.",
    )
    sl_token_url: str = Field(
        default=DEFAULT_TOKEN_URL,
        description="OAuth2 token endpoint (client-credentials grant).",
        max_length=2048,
    )

    # === API surface =====================================================
    sl_base_url: str = Field(
        default=DEFAULT_API_BASE_URL,
        description="Smart Accounts & Licensing v2 API base URL.",
        max_length=2048,
    )
    sl_smart_account_domain: str | None = Field(
        default=None,
        description="Default Smart Account domain (e.g. 'example.cisco.com'). Optional.",
        max_length=256,
    )
    sl_user_id: str | None = Field(
        default=None,
        description=(
            "Default CCO user id for the 'search-smart-accounts' role lookup "
            "(the userId query param). Optional; can be passed per-call instead."
        ),
        max_length=256,
    )
    sl_allow_custom_host: bool = Field(
        default=False,
        description="Allow token/API hosts outside the *.cisco.com allowlist. Off by default.",
    )

    # === Operational controls ============================================
    sl_enable_writes: bool = Field(
        default=False,
        description=(
            "When False (default), mutating tools are NOT registered. "
            "This server is read-only-by-construction for license inventory."
        ),
    )
    sl_evidence_dir: str | None = Field(
        default=None,
        description="Optional dir: each successful tool call writes a redacted JSON snapshot.",
        max_length=4096,
    )

    # === HTTP client tuning ==============================================
    http_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    http_max_retries: int = Field(default=3, ge=0, le=10)

    # === Token cache tuning ==============================================
    sl_token_refresh_skew_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Refresh the access token this many seconds before it expires.",
    )

    # === Logging / transport =============================================
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    mcp_transport: TransportName = "stdio"
    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = Field(default=8765, ge=1, le=65535)

    # ------------------------------------------------------------------
    @field_validator("sl_token_url", "sl_base_url")
    @classmethod
    def _normalize_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https":
            raise ValueError("URLs must use https://")
        if not parsed.netloc:
            raise ValueError("URLs must include a host")
        return value

    @model_validator(mode="after")
    def _check(self) -> Settings:
        # Credentials must come as a complete pair (or both unset for smoke boot).
        if (self.sl_client_id is None) != (self.sl_client_secret is None):
            raise ValueError(
                "SL_CLIENT_ID and SL_CLIENT_SECRET must be set together, or both unset."
            )
        # SSRF allowlist for token + API hosts.
        for label, url in (("SL_TOKEN_URL", self.sl_token_url), ("SL_BASE_URL", self.sl_base_url)):
            host = urlparse(url).hostname or ""
            if not self.sl_allow_custom_host and not any(
                host.endswith(sfx) for sfx in TRUSTED_HOST_SUFFIXES
            ):
                raise ValueError(
                    f"{label} host {host!r} is outside the *.cisco.com allowlist. "
                    "Set SL_ALLOW_CUSTOM_HOST=true to override (SSRF guard)."
                )
        return self

    @property
    def has_credentials(self) -> bool:
        return self.sl_client_id is not None and self.sl_client_secret is not None


def load_settings() -> Settings:
    """Load and validate settings from the process environment."""
    return Settings()  # type: ignore[call-arg]
