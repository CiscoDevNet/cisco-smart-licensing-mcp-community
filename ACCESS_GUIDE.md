# Getting API access for cloud CSSM Smart Licensing

This is the click-by-click guide to obtain the `client_id` / `client_secret`
that `cisco-smart-licensing-mcp` needs. It assumes you are a **user/admin on the
target Smart Account(s)** — that's the main prerequisite. If you're an admin on
those accounts, the self-service portal can issue keys quickly; the
email-approval fallback can take hours-to-days.

There are **two things you need, and both are required**:

1. **Create an app** (Type = API) to get `client_id` + `client_secret`.
2. **Associate the Software APIs to that app** via **Request Access**. Until this
   is Approved the app shows **Registered APIs = 0** and every call returns
   `403 "Invalid Client"` — even though token generation succeeds.

The self-service **Cisco IT API Portal** does both in one place (preferred); an
**email-approval** fallback is described under Step 1.

> **Don't use `apiconsole.cisco.com` for these APIs.** The generic API Console
> does not publish the cloud CSSM **Software APIs** surface this server targets —
> the licensing entry won't appear in its "Select APIs" list. Use the IT API
> Portal below. (Also don't pick lookalikes such as *CX Cloud Inventory V2* —
> that's CX/device inventory, not license inventory.)

Even after everything is approved, allow **~30 minutes** for a newly created
client to propagate before the token endpoint stops returning `401`, and note
that inventory calls return `403` until the Smart Account entitlement lands.

> **Heads-up on the mailer:** `smart-operations@cisco.com` sometimes bounces
> (the alias is periodically rerouted). If it does, route the same request
> through your internal Cisco contact / Smart Account approver, or open a case
> from **software.cisco.com → Support**. The information you need to provide is
> identical (below).

---

## How the platform is structured (30-second primer)

Three planes cooperate on every call — knowing the split makes the errors obvious:

| Plane | Host | Role |
| --- | --- | --- |
| **Identity** | `id.cisco.com` | Issues an OAuth2 token from your `client_id`/`client_secret`. |
| **API gateway** | `apx.cisco.com` | Checks your **app is subscribed** to the Software APIs (SLA tier), then proxies. |
| **Backend / CSSM** | behind the gateway | The Smart Licensing data itself. |

This server authenticates **machine-to-machine** (OAuth2 *client-credentials*
grant): no SSO, no user password, no MFA in the request path — the *application*
is the identity, and a short-lived Bearer token is minted per hour.

---

## Prerequisites

- A **Cisco.com (CCO) ID** that is a **user/admin on the target Smart Account**.
- Your **Smart Account domain name**. Find it at
  <https://software.cisco.com> → **Manage Smart Account** → the domain looks
  like `yourcompany.com` or `something.cisco.com`. Write it down; you need it
  in the access-request email.

---

## Step 1 — Request Smart Account API access

> **It's a TWO-step process** (this trips everyone up): (1) create/register the
> application to get a Client ID/Secret, then (2) **separately associate the
> Software APIs to that app** via **Request Access** (pick API Instance = `prod`,
> your Application, an SLA tier, and a reason). Until step 2 is Approved the app
> shows **Registered APIs = 0** and every call returns `403 "Invalid Client"` —
> even though token generation succeeds. After approval (Registered APIs ≥ 1),
> calls work immediately.

### Preferred: self-service via the Licensing Developer portal

Per Cisco's licensing team, all licensing APIs — and a **Request Access**
section that issues credentials — live here:

  <https://it-developer.cisco.com/auth/customer-assets/licensing/apis/latest/>

Sign in with your CCO ID, open **Request Access**, and request API
credentials (`client_id` / `client_secret`). Because access is scoped to your
CCO ID, **if you are an admin on the target Smart Accounts you can query them
once the keys are issued** — no per-Smart-Account email approval is needed.

This portal is SSO-gated, so grab these details while you're logged in (they
drive the `.env`): the documented **token endpoint**, the **API base URL/host**,
and the **license/inventory endpoint paths**. Any `*.cisco.com` host works with
this server via `SL_TOKEN_URL` / `SL_BASE_URL` — no code change needed.

### Fallback: email approval

If the portal's Request Access isn't available to you, email
**`smart-operations@cisco.com`** (or your internal Cisco contact / a
software.cisco.com support case if the alias bounces) with:

- **Subject:** `Smart Accounts & Licensing API access request — CCO ID <you>`
- **CCO ID:** your cisco.com username
- **OAuth grant type:** Client Credentials (API Service app)
- **Application name:** `smart-licensing`
- **Purpose:** read-only license inventory automation (MCP server)
- **Smart Account domain name(s):** the domain(s) you need, e.g.
  - `something-test.cisco.com`  *(a test/demo SA is ideal for least-privilege)*
  - `yourcompany.com`  *(request only what you actually need)*

You must already hold a **Smart Account User/Admin role** on each domain
(check software.cisco.com → Manage Smart Account). Cisco typically confirms
within **24 hours** (sometimes a few days).

---

## Step 2 — Create the application and associate the APIs

Do this in the **Cisco IT API Portal**
(<https://it-developer.cisco.com/auth/customer-assets/licensing/apis/latest/>).
It's a **two-step** flow — both parts are required.

### 2a. Create the application (get keys)

1. Sign in with your CCO ID and open **My Applications → Create Application**.
2. Set **Application Type = API** (the machine-to-machine / service type).
3. Click **Generate Client ID & Secret** (self-supplied secrets aren't allowed).
4. Copy the **Client ID** and **Client Secret** into your `.env` (Step 4).
   - Treat the secret like a password — **never** paste it into source, chat, or
     `mcp.json`. You can return later to view/rotate them.

At this point the app shows **Registered APIs = 0**: it has keys but is **not yet
subscribed** to any API, so calls will return `403 "Invalid Client"`.

### 2b. Associate the Software APIs (Request Access)

1. Open the **Request Access** section.
2. Choose **API Instance = `prod`**, your **Application**, an **SLA Tier**, and a
   short **reason**.
3. Submit. For internal/admin users this is typically approved immediately.
4. The app now shows **Registered APIs ≥ 1** (e.g. `prod` + `test`, both
   **Approved**).

Once **Registered APIs ≥ 1**, both token generation **and** API calls succeed.

---

## Step 3 — Verify the token + a first API call (curl)

Once Step 2 is done (and after the ~30-min propagation), test the token grant.
Replace the placeholders; do **not** commit this command with real values.

```bash
# Current IdP endpoint (used by newly registered apps):
curl --location --request POST \
  'https://id.cisco.com/oauth2/default/v1/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode "client_id=${SL_CLIENT_ID}" \
  --data-urlencode "client_secret=${SL_CLIENT_SECRET}"
```

Expected: JSON with `"access_token": "..."` and `"expires_in": 3599`.

- **401 `invalid_client`** right after registering → wait ~30 min and retry
  (client still propagating), and double-check the id/secret.
- If your app was minted on the legacy IdP, use
  `https://cloudsso.cisco.com/as/token.oauth2` instead.

Then confirm the API itself (base `https://apx.cisco.com/v1/software/apis`,
from the Software APIs OpenAPI spec):

```bash
TOKEN='paste-access-token-here'
curl --location \
  "https://apx.cisco.com/v1/software/apis/accounts/v1/user/search-smart-accounts?userId=${SL_USER_ID}&addVirtualAccounts=true" \
  --header "Authorization: Bearer ${TOKEN}"
```

- **200** with your Smart/Virtual accounts → you're fully set. 🎉
- **403** → token works but Smart Account API access (Step 1) isn't approved yet.

---

## Step 4 — Wire it into the MCP server

```bash
cd /path/to/cisco-smart-licensing-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` and set:

```
SL_CLIENT_ID=...your client id...
SL_CLIENT_SECRET=...your client secret...
SL_USER_ID=<your-cco-id>                     # default userId for list-smart-accounts
SL_SMART_ACCOUNT_DOMAIN=yourcompany.com      # optional convenience default
# SL_TOKEN_URL=https://cloudsso.cisco.com/as/token.oauth2   # only if legacy IdP
```

`.env` is git-ignored. The wrapper `scripts/run-cursor.sh` loads it into the
process environment; the credentials never touch `mcp.json` or the command line.

Register in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cisco-smart-licensing": {
      "command": "/path/to/cisco-smart-licensing-mcp/scripts/run-cursor.sh"
    }
  }
}
```

Reload MCP servers in Cursor, then try **`sl_list_smart_accounts`**.

---

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| `401 invalid_client` on token | client still propagating / wrong secret | wait ~30 min; re-copy id+secret |
| Token OK but API `403 "Invalid Client"` | app has **0 Registered APIs**, or client still propagating | in the portal, edit the app and register/subscribe the **Software APIs** (Registered APIs must be ≥ 1); then wait ~30 min |
| Token OK, API `403` | Step 1 (SA entitlement) not approved for this SA | wait for smart-operations@cisco.com / internal-contact confirmation |
| API `404` on a specific inventory path | wrong/relative path | confirm the exact path in the Software APIs docs/spec |
| Server registers 0 tools | `.env` missing creds | set `SL_CLIENT_ID` + `SL_CLIENT_SECRET` |
| Token endpoint unreachable | wrong IdP host | try the legacy `cloudsso.cisco.com/as/token.oauth2` |

## Security reminders

- The `client_secret` is a bearer-equivalent credential. Keep it only in `.env`
  (git-ignored) or a secret manager. This repo redacts tokens/secrets in logs
  and evidence files, and keeps TLS verification **on** for both the token
  endpoint and `apx.cisco.com`.
- Request the **least-privileged** access that satisfies read-only inventory.
  This server ships no mutating tools (`SL_ENABLE_WRITES` stays `false`).
