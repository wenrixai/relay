## MODIFIED Requirements

### Requirement: Startup aborts on invalid config
The relay SHALL log the validation error and abort startup with a non-zero exit when configuration is
invalid. A configuration is invalid — and startup SHALL abort — when any configured channel resolves
to no upstream base: that is, when `proxy_pass` remains unset after per-type `host` defaulting (a
channel type with no default host that supplies neither `host` nor `proxy_pass`). The relay SHALL NOT
report such a channel as ready and then fail every request at forward time.

#### Scenario: Invalid config aborts
- **WHEN** the configured JSON config file fails model validation
- **THEN** the loader raises and startup does not complete

#### Scenario: Channel with no resolvable upstream aborts startup
- **WHEN** a channel of a type with no default host is configured without `host` or `proxy_pass`
- **THEN** startup aborts with an error naming the channel, rather than the relay booting ready and
  returning an internal error on every request to that channel
