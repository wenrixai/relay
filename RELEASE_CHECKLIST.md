# Release checklist

Releases are cut by pushing a `v*` tag; `.github/workflows/release.yml` does the rest.

## Before tagging

- [ ] `main` is green (CI + Security workflows passing).
- [ ] `just ci` passes locally (ruff, ruff-format, mypy strict, pylint, pytest + coverage gate).
- [ ] `CHANGELOG`-worthy commits follow Conventional Commits (the release notes derive from them).
- [ ] `uv.lock` is committed and consistent with `pyproject.toml`.
- [ ] Version chosen per SemVer (breaking → major, feature → minor, fix → patch).

## Tag and push

```bash
git checkout main && git pull
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

## What the workflow does (on `v*`)

1. Derives the version from the tag (`vX.Y.Z` → `X.Y.Z`).
2. Builds and pushes the Alpine image to `ghcr.io/<owner>/wenrix-relay:<version>` (and `:latest`).
3. Generates an SPDX SBOM with syft (`sbom.spdx.json`).
4. Optionally cosign-signs the image (keyless OIDC) when repo variable `COSIGN_ENABLED=true`.
5. Bumps the Helm chart `version`/`appVersion`, packages it, and pushes it to GHCR as an OCI chart.
6. Publishes a GitHub Release with a Conventional Commits changelog, attaching the SBOM and chart.

## After release

- [ ] Verify the image pulls: `docker pull ghcr.io/<owner>/wenrix-relay:<version>`.
- [ ] Verify the GitHub Release, SBOM asset, and chart `.tgz` are present.
- [ ] (If signing) `cosign verify` the image.
- [ ] Commit the bumped `Chart.yaml` to `main` if you want the source tree to reflect the release
      (the workflow bumps only the packaged artifact, not the branch).

## Prerequisites (one-time)

- GHCR publishing uses the built-in `GITHUB_TOKEN` (`packages: write`); no extra secret needed.
- To enable signing, set repository variable `COSIGN_ENABLED=true` (keyless — no key material).
- Branch protection: tags are not protected; ensure only maintainers can push tags.
