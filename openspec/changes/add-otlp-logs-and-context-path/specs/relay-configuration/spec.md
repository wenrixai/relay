## ADDED Requirements

### Requirement: Context-path root setting
The relay SHALL support a `RELAY_ROOT_PATH` process setting (default `""`) that configures a context
path under which the relay serves all its routes. The value SHALL be normalized: an empty value
SHALL remain empty (root-only serving, the default); a non-empty value SHALL be normalized to exactly
one leading `/` and no trailing `/` (e.g. `relay` and `/relay/` both normalize to `/relay`). The
setting SHALL be surfaced in the redacted `/admin/flare` diagnostics.

#### Scenario: Default is empty (root serving)
- **WHEN** `RELAY_ROOT_PATH` is unset
- **THEN** `root_path` is `""` and the relay serves routes at root as before

#### Scenario: Value normalized
- **WHEN** `RELAY_ROOT_PATH` is `relay` or `/relay/`
- **THEN** the normalized `root_path` is `/relay`

#### Scenario: Surfaced in diagnostics
- **WHEN** the `/admin/flare` diagnostics are rendered
- **THEN** the effective `root_path` is included
