# Credential Swap Process

Wenrix Relay replaces caller-provided supplier credentials with relay-managed credentials before
forwarding a request to the upstream supplier. Relay API basic authentication is separate from this
process; supplier credentials come from each channel's `credentials` object in the relay JSON config.

## Request flow

1. Caller sends a request to `/channel/{name}/{path}`.
2. `{name}` selects one configured channel from the JSON config.
3. Header hygiene rewrites the upstream `Host` and strips relay/forwarding headers.
4. If PII is enabled, request de-anonymization runs first.
5. If channel credentials are configured, the channel handler parses the XML body when needed,
   derives the operation from the body, and structurally swaps only the configured credential
   locations.
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
| `travelport` | `soap_security`, optional `soap_security_target_xpath` | Replaces SOAP `Header/Security`. |

Credential swap is opt-in. If `credentials` is empty, the request and response remain transparent
apart from the relay's normal header hygiene and any separately enabled PII processing.

## Failure modes

- Malformed XML on a request or response that must be inspected returns `502` with
  `X-Wenrix-Error: xml_parse_error`.
- Missing required credential fields or missing required XML credential targets return `502` with
  `X-Wenrix-Error: credential_swap_failed`.
- Oversize bodies that require inspection return `413`.
- Sabre and Amadeus response auth encryption requires a configured PII keyring because response auth
  fields are emitted as `ENC_` tokens.
