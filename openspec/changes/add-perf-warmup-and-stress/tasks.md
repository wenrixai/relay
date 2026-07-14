# Tasks — add warmup phase and stress/soak profiles to the perf harness

## 1. Warmup

- [ ] 1.1 Add a warmup phase to `perf/relay-load.js` whose samples are excluded from reported metrics — either a discarded ramp stage before measurement, a k6 `setup()` priming pass, or a scenario whose tag is filtered out of thresholds/summary. Prime the pool for every scenario channel.
- [ ] 1.2 Confirm steady-state p50/p95/p99 exclude the warmup window (verify in `summary.json`).

## 2. Profile selector

- [ ] 2.1 Add `PERF_PROFILE=load|stress|soak|spike` selecting the scenario set; default `load` keeps today's ramped run.

## 3. Stress profile

- [ ] 3.1 Add a `ramping-arrival-rate` (or ramping-VUs) stress scenario that climbs past the knee until error rate / p95 degrade; record the max sustained rps within `P95_BUDGET_MS` and the error rate there.

## 4. Soak profile

- [ ] 4.1 Add a soak scenario holding the target rate for a sustained window; assert error-rate stability.
- [ ] 4.2 Capture a memory-stability observation over the window (relay process/container metrics or a sampled RSS), reported in the summary.

## 5. Spike (optional)

- [ ] 5.1 Add a short spike scenario (sudden jump to N× target) to observe recovery.

## 6. CI + docs

- [ ] 6.1 `.github/workflows/perf.yml`: keep `load` as the default non-gating artifact; run stress/soak on a manual/nightly trigger (longer duration).
- [ ] 6.2 `perf/README.md`: document warmup, profiles, and how to read breaking-point/soak output.

## 7. Verify

- [ ] 7.1 Local `just perf` run with warmup produces a summary whose measured window excludes warmup.
- [ ] 7.2 `openspec validate add-perf-warmup-and-stress --strict`.
