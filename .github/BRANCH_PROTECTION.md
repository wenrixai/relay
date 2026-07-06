# Branch protection (manual GitHub setup)

Branch protection is a GitHub repository setting and cannot be committed. Configure it on
`master` (Settings → Branches → Branch protection rules):

- Require a pull request before merging; require approvals (≥1) and CODEOWNERS review.
- Require status checks to pass before merging, and require branches to be up to date:
  - `pre-commit` (ci.yml → `quality`)
  - `pytest` (ci.yml → `test`)
  - `Build image + readiness smoke` (ci.yml → `image`)
  - `CodeQL`, `gitleaks`, `Dependency audit`, `Trivy image scan` (security.yml)
- Require linear history; dismiss stale approvals on new commits.
- Do not allow direct pushes to `master`; no force-pushes.

These mirror the checks defined in `.github/workflows/` and the `no-commit-to-branch`
pre-commit hook.
