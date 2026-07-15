## ADDED Requirements

### Requirement: Local-only rules loading

The relay SHALL load the ruleset exclusively from the baked bundle shipped in the image
(`rules_fallback.json`). There SHALL be no runtime HTTP fetch of rules and no rules-API URL
setting. An incompatible `schema_version` SHALL be rejected wherever it appears. An invalid baked
bundle SHALL abort startup when any channel has PII enabled; without PII enabled it SHALL degrade to
"no rules loaded" (logged, not fatal).

#### Scenario: Baked bundle loads at startup
- **WHEN** the relay starts
- **THEN** the ruleset is parsed from the baked bundle and `rule_version` reports its
  `rules_version`
- **AND** no network request is made to load rules

#### Scenario: Invalid baked bundle aborts with PII enabled
- **WHEN** the baked bundle fails validation and any channel has `pii.enabled: true`
- **THEN** startup aborts with a non-zero exit

#### Scenario: Invalid baked bundle degrades without PII
- **WHEN** the baked bundle fails validation and no channel has PII enabled
- **THEN** the relay starts with no rules loaded, logging the failure

#### Scenario: No polling
- **WHEN** the relay runs after startup
- **THEN** no rules-related requests or re-reads occur

## REMOVED Requirements

### Requirement: Startup fetch with baked fallback
**Reason**: The remote rules-API fetch is removed; rules always load from the local baked bundle,
which is now the sole and permanent source, not a fallback for a failed fetch.
**Migration**: Remove any `RELAY_RULES_API_URL` configuration — it is no longer read. Rule updates
now ship by rebuilding the image with an updated `rules_fallback.json` and redeploying.
