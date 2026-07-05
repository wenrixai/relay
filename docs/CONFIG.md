# the relay-configuration spec — Wenrix Channel Relay (v2) Configuration Reference

Canonical reference for configuring the relay: precedence, the JSON config schema, server/env
settings, secret formats, and migration from every v1 `WP_*` variable. Config is defined by pydantic
models (`src/channel_relay/config/models.py`); the JSON Schema is generated from them
(`config/json_schema.py`). Invalid config aborts startup with the validation error.

---

## 1. Sources & precedence
The effective config is resolved in this order (later wins):

1. **Built-in defaults** (pydantic model defaults).
2. **JSON config file** (`RELAY_CONFIG_FILE`, default `/etc/wenrix/relay.json`) — the primary source.
3. **Legacy `WP_*` env vars** (deprecated) — synthesized into channel entries and server settings
   when present (§6). Used for backward compatibility with v1 deployments.
4. **`RELAY_*` env vars** — explicit overrides for scalar server settings (§4).

Secrets are never taken from the JSON file when a Secret/env source is available; see §5. If both a
JSON channel and a `WP_*`-synthesized channel resolve to the same `name`, the JSON entry wins and a
deprecation warning is logged.

---

## 2. Channel config (JSON)
Only `name` and `type` are required. Shown as YAML for readability; on disk it is JSON.

```yaml
channels:
  - name: travelfusion-fr          # required, unique
    type: travelfusion             # required; one of the supported types (§3)
    host: api.travelfusion.com     # optional; per-type default (§3)
    proxy_pass: https://api.travelfusion.com  # optional; overrides scheme+host
    timeouts: { connect: 30, read: 120 }      # optional; defaults §4
    credentials: {}                # optional; swap is a no-op when empty
    pii: { enabled: false }        # opt-in; default false
    authorization:                 # optional
      allowed_operations:
        - { operation: "Fare_GetFareRules", version: "^1.0" }
```

### 2.1 Field reference
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes | — | Unique; used in the route `/channel/<name>/...`. |
| `type` | enum | yes | — | See §3. Selects parser + swap behavior. |
| `host` | string | no | per-type (§3) | Upstream host; sets `Host` + SNI. |
| `proxy_pass` | url | no | `https://<host>` | Full upstream base; overrides scheme/host/path prefix. |
| `timeouts.connect` | int (s) | no | 30 | Per-endpoint connect timeout. |
| `timeouts.read` | int (s) | no | 120 | Per-endpoint read timeout. No retries on timeout. |
| `credentials` | object | no | `{}` | Per-type keys (§3); swap runs only when present. |
| `pii.enabled` | bool | no | false | Enables redaction/de-anonymization for the channel. |
| `authorization.allowed_operations` | list | no | `[]` (allow all) | `{operation, version}`; empty = no restriction. |
| `authorization.external` | object | no | absent | Advanced authz (later phase); `{url, strict}`. |

---

## 3. Channel types, defaults, credential keys
| `type` | Default `host` | Credential keys | Swap |
|---|---|---|---|
| `travelfusion` | api.travelfusion.com | `login_id`, `xml_login_id`, optional `supplier_parameters` | Structural LoginId/XmlLoginId in request; strip from response. |
| `ba-ndc-direct` | api.ba.com | `client_key` | Add `Client-Key` header. |
| `la-ndc-direct` | (per deployment) | `api_key`, optional `api_key_header` | Add API key header (`API-Key` by default). |
| `farelogix-aa` | aa.farelogix.com | `subscription_key` (or legacy `api_key`), `agent`, `username`, `password`, `agent_user`, `agent_password`, optional `agent_number` | `Ocp-Apim-Subscription-Key` + structural `tc/iden` and `tc/agent` attribute replacement. |
| `farelogix-lh` | lhg.farelogix.com | (same as AA) | Same. |
| `farelogix-ua` | ua.farelogix.com | (same as AA) | Same. |
| `farelogix-ek` | ek.farelogix.com | (same as AA) | Same. |
| `amadeus` | (per deployment) | `soap_security`, optional `soap_security_target_xpath` | Replace SOAP security header; response auth-field encryption. |
| `sabre` | (per deployment) | `soap_security`, optional `soap_security_target_xpath` | Replace SOAP security header; response auth-field encryption. |
| `travelport` | (per deployment) | `soap_security`, optional `soap_security_target_xpath` | Replace SOAP security header. |

---

## 4. Server / global env (`RELAY_*`)
| Env | Default | Notes |
|---|---|---|
| `RELAY_CONFIG_FILE` | `/etc/wenrix/relay.json` | Path to JSON config. |
| `RELAY_PORT` | 8080 | Listen port. |
| `RELAY_TLS_ENABLED` | false | Enable inbound TLS. |
| `RELAY_TLS_PORT` | 18443 | TLS listen port. |
| `RELAY_MTLS_ENABLED` | false | Opt-in client mTLS (verify against baked-in Wenrix cert). |
| `RELAY_BASIC_AUTH_ENABLED` | true | Default client auth. |
| `RELAY_DNS_RESOLVER` | 8.8.8.8 | Upstream DNS resolver. |
| `RELAY_DEFAULT_CONNECT_TIMEOUT` | 30 | Default per-channel connect timeout (s). |
| `RELAY_DEFAULT_READ_TIMEOUT` | 120 | Default per-channel read timeout (s). |
| `RELAY_MAX_INSPECT_BYTES` | 8388608 | Max inspectable body; exceed → 413 (§9.4/§10). |
| `RELAY_TELEMETRY_LOGS_ENABLED` | true | Toggle log export. |
| `RELAY_TELEMETRY_METRICS_ENABLED` | true | Toggle metric export. |
| `RELAY_OTLP_ENDPOINT` | Wenrix default | Override telemetry endpoint. |
| `RELAY_RULES_API_URL` | Wenrix default | Rules API; startup fetch, baked fallback (§8.8). |
| `RELAY_PII_KEYRING` | (none) | Inline keyring JSON `{epoch_int: base64key}` (§5). |
| `RELAY_PII_KEYRING_FILE` | (none) | Path to a mounted keyring file; wins over `RELAY_PII_KEYRING`. |
| `RELAY_PII_KEY_EPOCH_ACTIVE` | (highest present) | Active epoch for new encryptions. |
| `RELAY_DEBUG` | false | Verbose startup; never logs secrets/PII. |

---

## 5. Secret formats
Secrets are provided via mounted files (preferred) or env, never in the JSON config or ConfigMaps.

| Secret | Format | Source |
|---|---|---|
| PII master key(s) | base64(32 bytes) per key epoch; keyring `{epoch_int: base64key}` | K8s Secret, create-if-absent (Helm); mounted file or `RELAY_PII_KEYRING`. |
| Inbound TLS cert/key | base64(PEM) | K8s Secret / file. |
| Wenrix client cert (mTLS) | PEM, **baked into the image** (public cert only) | Image; private key never in the relay. |
| Basic-auth users | htpasswd file, or `RELAY_BASIC_AUTH_USER`/`RELAY_BASIC_AUTH_PASS` | Secret / file. |
| Channel credentials | strings per §3 | K8s Secret referenced by channel config. |

Key rotation: add a new epoch to the keyring, set `RELAY_PII_KEY_EPOCH_ACTIVE`; old epochs remain for
decrypting historical tokens. Never remove an epoch still present in outstanding tokens.

---

## 6. Migration from v1 `WP_*` (deprecated, still supported)
On startup the relay synthesizes config from these. All are optional; presence enables the mapping.

### 6.1 Server
| v1 variable | v2 mapping |
|---|---|
| `WP_SERVER_PORT` | `RELAY_PORT` |
| `WP_SERVER_RESOLVER` | `RELAY_DNS_RESOLVER` |
| `WP_SERVER_PROXY_PASS` | default `proxy_pass` for channels lacking one |
| `WP_SERVER_HTTP_USER` / `WP_SERVER_HTTP_PASS` | basic-auth user/pass (auth enabled) |
| `WP_SERVER_TLS_ENABLED` | `RELAY_TLS_ENABLED` |
| `WP_SERVER_TLS_CERTIFICATE` / `_KEY` | inbound TLS cert/key (base64 PEM) |
| `WP_SERVER_TLS_PORT` / `_SERVER_NAME` | `RELAY_TLS_PORT` / TLS server name |
| `WP_SERVER_DEBUG` | `RELAY_DEBUG` |

### 6.2 Channels
| v1 variable(s) | Synthesized channel |
|---|---|
| `WP_CHANNELS_TRAVELFUSION_LOGIN_ID`, `_XML_LOGIN_ID`, `_HOST`, `_PROXY_PASS`, `_SUPPLIER_PARAMETERS` | `{ name: default-travelfusion, type: travelfusion, host, proxy_pass, credentials:{login_id, xml_login_id, supplier_parameters} }` |
| `WP_CHANNELS_BA_HOST`, `_API_KEY`, `_MERCHANT_ID`, `_PROXY_PASS` | `{ name: default-ba, type: ba-ndc-direct, host, credentials:{client_key: api_key, merchant_id} }` |
| `WP_CHANNELS_FARELOGIX_AA_*` (`_HOST`, `_PROXY_PASS`, `_API_KEY`, `_AGENT`, `_USERNAME`, `_PASSWORD`, `_AGENT_USER`, `_AGENT_PASSWORD`) | `{ name: default-farelogix-aa, type: farelogix-aa, host, credentials:{...} }` |
| `WP_CHANNELS_FARELOGIX_LH_*` | `{ name: default-farelogix-lh, type: farelogix-lh, ... }` |
| `WP_CHANNELS_FARELOGIX_UA_*` | `{ name: default-farelogix-ua, type: farelogix-ua, ... }` |
| `WP_CHANNELS_FARELOGIX_EK_*` | `{ name: default-farelogix-ek, type: farelogix-ek, ... }` |

Each synthesized channel logs a one-time deprecation warning. A parity test asserts a representative
v1 env set produces an equivalent JSON config. New channels (LA NDC, Amadeus, Sabre, Travelport) are
JSON-only; there is no v1 `WP_*` equivalent.

---

## 7. Example (JSON)
```json
{
  "channels": [
    { "name": "ba", "type": "ba-ndc-direct", "credentials": { "client_key": "..." },
      "pii": { "enabled": true } },
    { "name": "amadeus", "type": "amadeus", "host": "nodeD1.test.webservices.amadeus.com",
      "credentials": { "soap_security": "<wsse:Security>...</wsse:Security>" },
      "pii": { "enabled": true },
      "authorization": { "allowed_operations": [ { "operation": "PNR_Retrieve", "version": "^1.0" } ] } },
    { "name": "passthrough-x", "type": "travelport" }
  ]
}
```
`passthrough-x` has no credentials and no PII: a pure transparent relay for that channel.
