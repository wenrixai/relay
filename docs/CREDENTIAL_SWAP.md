# Credential Swap Process

Wenrix Relay replaces caller-provided supplier credentials with relay-managed credentials before
forwarding a request to the upstream supplier. Relay API basic authentication is separate from this
process; supplier credentials come from each channel's `credentials` object in the relay JSON config.
Credential swap runs only when `credentials.enabled` is explicitly set to `true`.

## Request flow

1. Caller sends a request to `/channel/{name}/{path}`.
2. `{name}` selects one configured channel from the JSON config.
3. Header hygiene rewrites the upstream `Host` and strips relay/forwarding headers.
4. Request de-anonymization runs when PII is enabled or when an encrypted supplier session token
   must be replayed.
5. If channel credential swap is enabled, the channel handler injects configured credential headers
   and, when needed, parses the XML body and structurally swaps only configured credential locations.
6. The upstream request is sent to `{channel.proxy_pass}/{path}` with no retries.
7. Response credential cleanup runs before normal PII response redaction.

## Channel behavior

| Channel type | Configured credential fields | Swap target |
| --- | --- | --- |
| `travelfusion` | `login_id`, `xml_login_id`, optional `supplier_parameters` as `name=value,name2=value2` | `{Operation}/LoginId`, `{Operation}/XmlLoginId`, and optional `{Operation}/CustomSupplierParameterList`; response login fields are removed. |
| `ba-ndc-direct` | `client_key` | Outbound `Client-Key` header. |
| `la-ndc-direct` | `api_key`, optional `api_key_header` | Outbound API key header; default header name is `API-Key`. |
| `farelogix-aa`, `farelogix-lh`, `farelogix-ua`, `farelogix-ek` | `subscription_key` or legacy `api_key`, `username`, `password`, `agent`, `agent_user`, `agent_password`, optional `agent_number` | Outbound `Ocp-Apim-Subscription-Key`; XML `tc/iden` attributes `u`, `p`, `agt`, `agtpwd`, optional `agy`; XML `tc/agent` attribute `user`. |
| `amadeus` | `soap_security`, optional `soap_security_target_xpath` | Replaces SOAP `Header/Security`; response auth fields are encrypted. |
| `sabre` | `soap_security`, optional `soap_security_target_xpath` | Replaces SOAP `Header/Security`; response auth fields are encrypted. |
| `travelport` | `username`, `password` | Replaces caller `Authorization` case-insensitively with Basic encoding of `Universal API/<username>:<password>`; SOAP auth/session elements are not replaced. Response `SessionKey` and `SessTok/@id` values are encrypted. |

Credential swap is opt-in. If `credentials.enabled` is omitted or false, the request and response
remain transparent apart from the relay's normal header hygiene and any separately enabled PII
processing, even if credential fields are present.

### Travelport Universal API migration

Travelport Universal API uses HTTP Basic authentication even though its payloads are SOAP/XML.
Enabled Travelport channels must configure the bare assigned username and password:

```json
{
  "name": "travelport-prod",
  "type": "travelport",
  "proxy_pass": "https://emea.universal-api.travelport.com/B2BGateway/connect/uAPI",
  "credentials": {
    "enabled": true,
    "username": "ASSIGNED_USERNAME",
    "password": "SECRET_FROM_RUNTIME_STORE"
  }
}
```

The relay adds `Universal API/` to the username and Base64-encodes the complete user/password pair.
Do not pre-encode the value or include the prefix in `username`.

This is a breaking correction for Travelport configurations: remove `soap_security`,
`soap_username`, and `soap_password`. The relay rejects those obsolete keys at startup. Because
Travelport session keys are returned as reversible `ENC_` tokens and restored in both
`SessTok/@id` and request `SessionKey` attributes, enabled Travelport credential swap also requires
the existing PII keyring even when `pii.enabled` is false.

## Failure modes

- Malformed XML on a request or response that must be inspected returns `502` with
  `X-Wenrix-Error: xml_parse_error`.
- Missing required credential fields or missing required XML credential targets return `502` with
  `X-Wenrix-Error: credential_swap_failed`.
- Oversize bodies that require inspection return `413`.
- Sabre, Amadeus, and Travelport response auth encryption requires a configured PII keyring because
  response auth fields are emitted as `ENC_` tokens.
