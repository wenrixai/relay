## ADDED Requirements

### Requirement: Context-path serving
When `RELAY_ROOT_PATH` is set (see relay-configuration), the relay SHALL serve every route it
exposes — the data-plane routes (`/channel/{name}`, `/channel/{name}/{path}`), the health probes
(`/liveness`, `/readiness`), and the admin route (`/admin/flare`) — under that context path. The
mechanism SHALL tolerate both load-balancer behaviors without reconfiguration: whether the upstream
forwards the full path including the prefix, or strips the prefix before forwarding. Channel matching
and upstream URL construction SHALL be unaffected by the context path — the path forwarded to the
channel SHALL be identical to the path forwarded when no context path is configured. When
`RELAY_ROOT_PATH` is empty, routing SHALL be byte-for-byte the current root-only behavior.

#### Scenario: Prefixed request routes and forwards
- **WHEN** `RELAY_ROOT_PATH` is `/relay` and a request hits `/relay/channel/<name>/<path>`
- **THEN** it routes to the channel and forwards to the channel's upstream base with the same
  `<path>`/query as an unprefixed `/channel/<name>/<path>` request would

#### Scenario: Stripped request still routes
- **WHEN** `RELAY_ROOT_PATH` is `/relay` and the load balancer strips the prefix so the relay
  receives `/channel/<name>`
- **THEN** it routes to the channel exactly as it does today

#### Scenario: Health probe reachable under the context path
- **WHEN** `RELAY_ROOT_PATH` is `/relay`
- **THEN** `GET /relay/liveness` returns 200 and `GET /relay/readiness` reports readiness

#### Scenario: Empty context path preserves root routing
- **WHEN** `RELAY_ROOT_PATH` is empty
- **THEN** routes are served only at root (`/channel/...`, `/liveness`, ...) as before
