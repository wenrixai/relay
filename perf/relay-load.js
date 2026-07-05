// k6 load/perf harness for the Wenrix Channel Relay (PROJECT.md §13.4).
//
// Four scenarios, run as separate k6 scenarios so each reports independently:
//   passthrough  — zero-config channel, no inspection
//   swap         — credential-swap channel (body parsed + structurally edited)
//   redact       — PII redaction enabled on the response
//   roundtrip    — request carries ENC_ tokens (de-anonymized) + response redaction
//
// Payload matrix (2KB / 32KB / 256KB) is selected per run via PAYLOAD_SIZE so results stay
// comparable; ramped VUs (1 -> 64) find the knee. The upstream is a mock with fixed injected
// latency (MOCK_LATENCY_MS) so measurements isolate relay overhead.
//
// Target: >= 50 rps/instance @ 1000m vCPU, error rate < 0.1%, p95 within the latency budget.
// Results are written to summary.json (a non-gating CI artifact).
//
// Usage:
//   k6 run -e RELAY_URL=http://127.0.0.1:8080 -e PAYLOAD_SIZE=2048 \
//          -e BASIC_AUTH=user:pass perf/relay-load.js

import http from "k6/http";
import encoding from "k6/encoding";
import { check } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.4/index.js";

const RELAY_URL = __ENV.RELAY_URL || "http://127.0.0.1:8080";
const PAYLOAD_SIZE = parseInt(__ENV.PAYLOAD_SIZE || "2048", 10);
const BASIC_AUTH = __ENV.BASIC_AUTH || ""; // "user:pass" or empty
// Latency budget (ms) at p95 above the fixed mock upstream latency.
const P95_BUDGET_MS = parseInt(__ENV.P95_BUDGET_MS || "150", 10);

// Channel names must exist in the relay config used for the run.
const CHANNELS = {
  passthrough: __ENV.CH_PASSTHROUGH || "passthrough",
  swap: __ENV.CH_SWAP || "swap",
  redact: __ENV.CH_REDACT || "redact",
  roundtrip: __ENV.CH_ROUNDTRIP || "roundtrip",
};

// A representative SOAP-ish XML body padded to PAYLOAD_SIZE. For roundtrip we embed an ENC_ token
// so the relay exercises de-anonymization on the request path.
function buildBody(withToken) {
  const token = withToken ? "ENC_AAAAAAAAAAAAAAAAAAAAAAAAAAAA" : "PLACEHOLDER";
  const head =
    '<?xml version="1.0"?><Envelope><Body><Order><PassengerName>' +
    token +
    "</PassengerName><Payload>";
  const tail = "</Payload></Order></Body></Envelope>";
  const padLen = Math.max(0, PAYLOAD_SIZE - head.length - tail.length);
  return head + "X".repeat(padLen) + tail;
}

function headers() {
  const h = { "Content-Type": "application/xml" };
  if (BASIC_AUTH) {
    h["Authorization"] = "Basic " + encoding.b64encode(BASIC_AUTH);
  }
  return h;
}

function hit(channel, body, tag) {
  const res = http.post(`${RELAY_URL}/channel/${channel}/`, body, {
    headers: headers(),
    tags: { scenario: tag },
  });
  check(res, { "status is 2xx/4xx (not 5xx)": (r) => r.status < 500 });
}

export function passthrough() {
  hit(CHANNELS.passthrough, buildBody(false), "passthrough");
}
export function swap() {
  hit(CHANNELS.swap, buildBody(false), "swap");
}
export function redact() {
  hit(CHANNELS.redact, buildBody(false), "redact");
}
export function roundtrip() {
  hit(CHANNELS.roundtrip, buildBody(true), "roundtrip");
}

const ramp = {
  executor: "ramping-vus",
  startVUs: 1,
  stages: [
    { duration: "20s", target: 8 },
    { duration: "20s", target: 32 },
    { duration: "30s", target: 64 },
    { duration: "10s", target: 0 },
  ],
  gracefulRampDown: "5s",
};

export const options = {
  scenarios: {
    passthrough: { ...ramp, exec: "passthrough", tags: { scenario: "passthrough" } },
    swap: { ...ramp, exec: "swap", tags: { scenario: "swap" }, startTime: "90s" },
    redact: { ...ramp, exec: "redact", tags: { scenario: "redact" }, startTime: "180s" },
    roundtrip: { ...ramp, exec: "roundtrip", tags: { scenario: "roundtrip" }, startTime: "270s" },
  },
  thresholds: {
    // Non-gating in CI (the workflow does not fail on these), but recorded for pass/fail review.
    http_req_failed: ["rate<0.001"],
    "http_req_duration{scenario:passthrough}": [`p(95)<${P95_BUDGET_MS}`],
    "http_req_duration{scenario:swap}": [`p(95)<${P95_BUDGET_MS}`],
    "http_req_duration{scenario:redact}": [`p(95)<${P95_BUDGET_MS}`],
    "http_req_duration{scenario:roundtrip}": [`p(95)<${P95_BUDGET_MS}`],
  },
};

export function handleSummary(data) {
  return {
    "summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: " ", enableColors: false }),
  };
}
