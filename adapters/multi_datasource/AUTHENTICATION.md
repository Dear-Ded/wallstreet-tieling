# Multi-DataSource Authentication Guide

This framework supports enterprise data sources that require authentication,
session state, request signing, token refresh, or human-verification handling.

Default behavior is safe: challenge automation is not enabled by default. When a
human-verification challenge is detected, the framework returns structured
metadata so the UI, browser plugin, or an enterprise-approved provider can take
over.

## Supported Auth Types

- `none`: no authentication.
- `basic`: HTTP Basic authentication.
- `api_key`: sends an API key in a header or query parameter.
- `bearer`: sends `Authorization: Bearer <token>`.
- `session`: sends configured session headers and cookies.
- `request_signature` / `hmac`: signs each request with a timestamped HMAC.
- `oauth2`: bearer token with refresh-required detection.
- `challenge_aware`: session/bearer support plus human-verification detection.

## Simple Examples

API key in a header:

```yaml
auth:
  type: api_key
  api_key: "${PUBLIC_DATA_API_KEY}"
  header_name: "X-API-Key"
```

Bearer token:

```yaml
auth:
  type: bearer
  token: "${PUBLIC_DATA_TOKEN}"
```

Session cookies:

```yaml
auth:
  type: session
  cookies:
    sessionid: "${PUBLIC_DATA_SESSION_ID}"
  session_headers:
    X-Requested-With: "XMLHttpRequest"
```

Request signing:

```yaml
auth:
  type: request_signature
  signature_secret: "${PUBLIC_DATA_SIGNING_SECRET}"
  signature_header: "X-Signature"
  timestamp_header: "X-Timestamp"
  signature_algorithm: "sha256"
```

Challenge-aware source:

```yaml
auth:
  type: challenge_aware
  token: "${USER_AUTHORIZED_TOKEN}"
  cookies:
    sid: "${USER_AUTHORIZED_SESSION_ID}"
  challenge_provider: disabled
```

If a CAPTCHA or similar human-verification challenge is detected, the query
returns `metadata.auth_challenge`:

```json
{
  "auth_challenge": {
    "type": "human_verification",
    "source": "example_source",
    "details": {
      "handling": "requires configured compliant challenge provider or user authorization flow",
      "provider": {
        "provider": "disabled",
        "status": "provider_not_configured",
        "next_action": "configure_provider_or_user_authorization",
        "metadata": {
          "automation_enabled": false,
          "default_safe": true
        }
      }
    }
  }
}
```

## Product Behavior For Non-Technical Users

- Most users do not need to configure authentication manually.
- Safe public sources can run with `auth.type: none`.
- If a source requires authorization, the UI should ask the user to connect that
  source or ask an administrator to configure a provider.
- The framework should explain what is needed instead of exposing protocol
  details.

## Provider Slot

Human-verification handling is a provider slot. Enterprises can attach their own
approved provider according to their legal, compliance, and deployment rules.
The built-in framework detects and reports challenges; it does not bypass access
controls.

Built-in provider slots:

- `disabled`: default-safe behavior. It returns structured challenge metadata
  and asks the product/UI layer to connect an approved provider or user
  authorization flow.
- `browser_handoff`: returns a handoff contract for an authorized browser or
  plugin flow. It does not solve, bypass, or submit CAPTCHA challenges by
  itself.

Browser handoff example:

```yaml
auth:
  type: challenge_aware
  challenge_provider: browser_handoff
  challenge_provider_config:
    session_scope: source
    handoff_url: "https://example.com/login"
    callback_url: "http://127.0.0.1:8765/auth/callback"
```

Provider implementations should:

- keep source provenance and user authorization evidence;
- avoid storing passwords or raw browser cookies in the repository;
- redact secrets in logs and query results;
- document the legal basis and operational owner for the provider;
- be disabled by default unless explicitly configured.

## Security Notes

- Store secrets in environment variables or a secret manager.
- Do not commit tokens, cookies, private keys, or captured browser sessions.
- Use `ping` and health checks to detect expired sessions early.
- Treat public-web and bot-delivered results as leads until URL-level evidence is
  verified.
