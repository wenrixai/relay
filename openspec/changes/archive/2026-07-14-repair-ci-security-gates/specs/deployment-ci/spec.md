## MODIFIED Requirements

### Requirement: Security automation
The repository SHALL configure Dependabot, CodeQL, gitleaks, dependency audit, and Trivy image
scanning, plus CODEOWNERS and a PR template. Security jobs SHALL execute on organization pull
requests using standard repository credentials and SHALL fail on security findings rather than
missing optional commercial scanner credentials or invalid local-project dependency resolution.

#### Scenario: Security workflows present
- **WHEN** the repository is scanned
- **THEN** Dependabot, CodeQL, gitleaks, dependency audit, and Trivy jobs are configured

#### Scenario: Security jobs execute on dependency-update pull requests
- **WHEN** an organization dependency bot opens a pull request
- **THEN** CodeQL can check out and analyze the repository, gitleaks scans the checked-out history
  without an optional license secret, and dependency audit scans the locked third-party production
  dependencies without attempting to install the editable relay project
