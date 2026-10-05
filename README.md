# cisco-smart-licensing-mcp-community

A community **Model Context Protocol (MCP)** server for the Cisco cloud **Smart
Software Manager (CSSM)** license inventory —
[`software.cisco.com/#SmartLicensing-Inventory`](https://software.cisco.com/#SmartLicensing-Inventory).

It exposes **read-only** tools for Smart Accounts, Virtual Accounts, and their
license entitlements.

## Why not just scrape the web UI?

The CSSM inventory page sits behind **Cisco SSO** (SAML + MFA). Automating that
login is brittle and against the spirit of the platform. Instead this server
uses Cisco's official **machine-to-machine OAuth 2.0 client-credentials** flow:

```
client_id + client_secret ──► id.cisco.com token endpoint ──► short-lived Bearer token
                                                               │
                              Cisco "Software APIs" (apx.cisco.com) ◄┘
```

Base URL, token endpoint, and endpoint paths are taken from Cisco's official
**Software APIs** OpenAPI spec (v1.0.2): base `https://apx.cisco.com/v1/software/apis`,
token endpoint `https://id.cisco.com/oauth2/default/v1/token`, OAuth2
client-credentials grant.

No human login, SAML, or MFA is ever in the request path. You get the
client_id/secret by registering an app on the
[Licensing Developer portal](https://it-developer.cisco.com/auth/customer-assets/licensing/apis/latest/)
— see **[ACCESS_GUIDE.md](./ACCESS_GUIDE.md)** for the exact click-by-click steps.

## Architecture

| Concern            | Where                                   |
| ------------------ | --------------------------------------- |
| Config (env only)  | `src/cisco_smart_licensing_mcp/config.py` |
| OAuth2 token cache | `auth.py` (`ClientCredentialsTokenProvider`) |
| REST client        | `client.py` (retries, 401 re-auth, SSRF allowlist) |
| Tool registration  | `registry.py` |
| Tools              | `tools/accounts.py`, `tools/inventory.py` |
| Logging (redacted) | `logging.py` |

- **Transport:** stdio by default (per MCP security guidance). HTTP is opt-in
  and binds to 127.0.0.1 only.
- **Read-only by construction:** mutating tools are not registered unless
  `SL_ENABLE_WRITES=true` (there are none in v0.1).
- **Secrets:** `client_secret` is a `SecretStr`, sourced from the environment,
  never logged, never written to disk. Tokens/JWTs are redacted in logs and in
  optional evidence snapshots.
- **SSRF guard:** token + API hosts must end in `.cisco.com`; the passthrough
  tool accepts relative paths only.

## Tools

All read-only, mapped to confirmed GET endpoints in the Software APIs spec:

| Tool                             | Endpoint |
| -------------------------------- | -------- |
| `sl_list_smart_accounts`         | `GET /accounts/v1/user/search-smart-accounts` |
| `sl_list_virtual_accounts`       | `GET /pnp/v2/accounts/{smartAccountDomain}/virtual-accounts` |
| `sl_search_product_instances`    | `GET /licensing/v2/accounts/{smartAccountDomain}/devices` |
| `sl_get_subscription_consumption`| `GET /ea/v1/subscription/account/{smartAccountDomain}/consumption` |
| `sl_get_license_inventory`       | GET passthrough to any confirmed relative path (escape hatch) |

> **More endpoints available.** The spec has 130 operations (license summary,
> history, SLR reservations, tokens, PnP devices, etc.). The passthrough
> (`sl_get_license_inventory`) reaches any read-only one today; high-value ones
> can be promoted to named tools on request. Note `POST /licensing/v2/get-summary`
> needs numeric `X-CSW-SMART-ACCOUNT-ID` / `X-CSW-VIRTUAL-ACCOUNT-ID` headers, so
> it's intentionally left for a dedicated tool.

## Install

```bash
git clone https://github.com/CiscoDevNet/cisco-smart-licensing-mcp-community.git
cd cisco-smart-licensing-mcp-community
python -m venv .venv
source .venv/bin/activate
pip install -e .            # add ".[dev]" for tests/linting
cp .env.example .env        # then fill in SL_CLIENT_ID / SL_CLIENT_SECRET
```

Register in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cisco-smart-licensing": {
      "command": "/path/to/cisco-smart-licensing-mcp-community/scripts/run-cursor.sh"
    }
  }
}
```

## Smoke test (no credentials needed)

With an empty `.env`, the server boots and registers **zero** tools — this
verifies the binary and wiring without any tenant:

```bash
.venv/bin/cisco-smart-licensing-mcp   # Ctrl-C to exit; watch stderr for "boot complete"
```

## Tests

All tests are offline (HTTP is mocked with `pytest-httpx`); no Cisco credentials
are needed:

```bash
pip install -e ".[dev]"
pytest
```

## Getting access

You have a Smart Account and admin rights but no API app yet. Follow
**[ACCESS_GUIDE.md](./ACCESS_GUIDE.md)** — it walks you through creating the
client-credentials app, associating the Software APIs via **Request Access**,
and the ~30-minute propagation window.

## Contributing, security, and license

- Contributions are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md) and the
  [Code of Conduct](./CODE_OF_CONDUCT.md).
- Please report security issues privately as described in [SECURITY.md](./SECURITY.md).
- Licensed under the [Apache License 2.0](./LICENSE).
