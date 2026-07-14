# Add a warmup phase and a stress/soak profile to the perf harness

## Why

`perf/relay-load.js` is a single ramped **load** test (VUs 1→64) with two gaps against the §13.4
methodology and sound benchmarking practice:

1. **No warmup.** Measurement starts cold: the first VUs pay one-time costs — httpx connection-pool
   fill, TLS handshakes, the once-at-startup rules load, Python import/allocation warmth — and those
   samples land directly in the reported p95/p99. The knee and the latency budget are measured against
   a polluted first window, so results are pessimistic and noisy run-to-run.

2. **No stress/soak/spike profile.** The harness never ramps **past** the knee to find the breaking
   point, never sustains a fixed rate long enough to observe memory growth, and never spikes. §13.4
   explicitly calls for a soak window ("no memory growth over a soak window") and a pass/fail at the
   target rps; neither is exercised. There is no way to answer "where does an instance fall over" or
   "does it leak under sustained load."

## What Changes

- **Warmup.** Add a warmup phase before measurement whose samples are excluded from the reported
  metrics — either a discarded warmup stage (ramp to a low steady rate, then reset) or a k6 `setup()`
  priming pass — so steady-state p50/p95/p99 exclude cold-start costs. Document the warmup duration.
- **Stress profile.** Add a stress scenario that ramps VUs (or arrival rate) well past the knee until
  error rate / latency degrade, reporting the breaking point (max sustained rps within the budget).
- **Soak profile.** Add a soak scenario holding the target rate for a sustained window, asserting no
  error-rate regression and (via the relay's process/memory metrics or container stats) no memory
  growth over the window.
- **Spike (optional).** A short spike scenario (sudden jump to a multiple of target) to observe
  recovery.
- Profiles selectable (e.g. `PERF_PROFILE=load|stress|soak|spike`) so each reports independently and
  the default CI run stays the fast, non-gating load artifact.

## Capabilities

### Modified Capabilities
- `deployment-ci`: the perf harness includes a warmup phase (excluded from measurement) and
  stress/soak profiles (breaking point + memory-stability over a soak window), alongside the existing
  ramped load run.

## Impact

- `perf/relay-load.js`: warmup stage/`setup` priming; stress/soak/spike scenarios behind a profile
  selector; keep results non-gating.
- `perf/README.md`: document warmup, profiles, and how to read the breaking-point/soak output.
- `.github/workflows/perf.yml`: keep the default load profile as the non-gating artifact; stress/soak
  as manual/nightly (they run longer).
