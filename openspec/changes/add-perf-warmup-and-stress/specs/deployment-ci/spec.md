## MODIFIED Requirements

### Requirement: Load and performance harness
The repository SHALL provide a k6 load/perf harness covering pass-through, credential-swap,
PII-redaction, and redaction-plus-de-anonymization round-trip scenarios across a 2KB/32KB/256KB
payload matrix with ramped virtual users, reporting p50/p95/p99 latency and error rate against a
fixed mock-upstream latency. Results SHALL be published as a CI artifact and SHALL be non-gating by
default.

The harness SHALL include a **warmup phase** whose samples are excluded from the reported metrics, so
steady-state p50/p95/p99 exclude one-time cold-start costs (connection-pool fill, TLS handshakes, the
startup rules load, interpreter warmth). The harness SHALL additionally provide a **stress** profile
that drives load past the knee to report the breaking point (maximum sustained rps within the latency
budget) and a **soak** profile that holds the target rate over a sustained window to confirm no
error-rate regression and no memory growth. Profiles SHALL be independently selectable; the default
CI run remains the ramped load profile (fast, non-gating), with stress/soak available as a
manual/nightly run.

#### Scenario: Perf run produces a non-gating artifact
- **WHEN** the perf harness runs in CI
- **THEN** a summary artifact with per-scenario p50/p95/p99 and error rate is published without
  failing the build

#### Scenario: Warmup samples are excluded from results
- **WHEN** the harness runs
- **THEN** a warmup phase precedes measurement and its samples are not counted in the reported
  p50/p95/p99

#### Scenario: Stress profile reports a breaking point
- **WHEN** the stress profile runs
- **THEN** it drives load past the knee and reports the maximum sustained rps within the latency
  budget and the error rate at that point

#### Scenario: Soak profile checks memory stability
- **WHEN** the soak profile holds the target rate over its window
- **THEN** it reports error rate and a memory-stability observation (no growth) over the window
