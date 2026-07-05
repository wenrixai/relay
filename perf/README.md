# Load / performance harness (PROJECT.md §13.4)

A k6 harness that measures relay overhead across four scenarios and a payload matrix. Results are a
CI artifact and are **non-gating by default**.

## Method

- **Scenarios** (reported separately): `passthrough`, `swap` (credential swap), `redact` (PII
  redaction on the response), `roundtrip` (request de-anonymization + response redaction).
- **Payload matrix**: 2KB / 32KB / 256KB — select per run with `PAYLOAD_SIZE` (bytes).
- **Concurrency**: ramped VUs 1 → 64 to find the knee; k6 reports p50/p95/p99 and error rate.
- **Fixed upstream latency**: the mock channel injects `MOCK_LATENCY_MS` (e.g. 50) so measurements
  isolate relay overhead from network/upstream time.
- **Target**: ≥ 50 rps/instance @ 1000m vCPU, error rate < 0.1%, p95 within the latency budget
  (`P95_BUDGET_MS`, above the fixed upstream latency).

## Run locally

```bash
# 1. Start the mock upstream with fixed latency.
MOCK_PORT=9000 MOCK_LATENCY_MS=50 uv run python deployment/mock_channel.py &

# 2. Start the relay with the perf channel config (basic auth off for simplicity).
RELAY_CONFIG_FILE=perf/relay.perf.json RELAY_BASIC_AUTH_ENABLED=false \
  RELAY_PII_KEYRING='{"0":"'$(head -c32 /dev/urandom | base64)'"}' RELAY_PII_KEY_EPOCH_ACTIVE=0 \
  uv run uvicorn channel_relay.main:app --port 8080 &

# 3. Run the harness for each payload size.
for size in 2048 32768 262144; do
  k6 run -e RELAY_URL=http://127.0.0.1:8080 -e PAYLOAD_SIZE=$size perf/relay-load.js
done
```

Or simply `just perf` (runs the 2KB profile against a locally-started stack).

## Output

`summary.json` (full k6 metrics) plus a text summary on stdout. Per-scenario p50/p95/p99 come from
`http_req_duration{scenario:...}`; error rate from `http_req_failed`.
