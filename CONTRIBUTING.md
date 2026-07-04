# Contributing

This is the canonical process document for Wenrix Channel Relay v2. Other files in the
repository reference this document rather than restating the process. Product requirements
live in `PROJECT.md`; the security policy and threat model live in `SECURITY.md`.

The repository lives in the `wenrixai` GitHub organization. The `main` branch is
protected.

## Definition of Done

A change is done when all of the following are true:

- [ ] Behavior is covered by tests, written first (see TDD Workflow below).
- [ ] The OpenSpec loop has been followed, or the change qualifies for a documented
      exemption (see OpenSpec below).
- [ ] `ruff` lint passes and `ruff format` has been applied.
- [ ] `mypy` passes in strict mode with type hints everywhere.
- [ ] `pylint` passes.
- [ ] `uv run pytest` passes, with no slow tests, and the coverage gate passes.
- [ ] `uv.lock` is committed and consistent with `pyproject.toml`.
- [ ] Commits follow Conventional Commits.
- [ ] The PR passes all required checks and, if non-trivial, has received a
      thermo-nuclear quality review.

## TDD Workflow

Test-driven development is mandatory. Tests are written first.

Follow **red-green-refactor**:

1. **Red**: write a failing test that expresses the desired behavior. Run it and confirm
   it fails for the expected reason.
2. **Green**: write the minimum code needed to make the test pass.
3. **Refactor**: clean up implementation and tests while keeping them green.

Do not write production code before there is a failing test that requires it.

## OpenSpec

We use OpenSpec to manage changes to specified behavior. See
https://github.com/Fission-AI/OpenSpec.

### The loop

1. **Propose**: create a change under `openspec/changes/<id>/` containing:
   - a **proposal** describing the motivation and approach,
   - a **spec delta** describing the change to the specification, and
   - a **task list** breaking the work into steps.
2. **Validate**: run `openspec validate` and resolve any errors before implementing.
3. **Implement**: build the change using the TDD workflow above.
4. **Archive**: when the change is complete, archive the delta into `openspec/specs/` so
   the specification reflects the shipped behavior.

### When OpenSpec is mandatory

OpenSpec is **mandatory** for anything touching:

- external behavior,
- security,
- configuration,
- channel contracts, or
- deployment.

### Exemptions

The following may **skip the proposal** but still require tests and green CI:

- scaffolding,
- typo fixes,
- test-only changes, and
- internal refactors (no change to external behavior).

Exempt changes still follow the Definition of Done: tests come first and all required
checks must pass.

## Tooling

- **Package manager: `uv` only.** Do not use `pip`. Use `uv add` to add dependencies and
  `uv sync` to install them. Keep `uv.lock` committed.
- **Lint and format: `ruff`.** Run `ruff` for linting and `ruff format` for formatting.
- **Types: `mypy` strict.** Type hints are required everywhere; strict mode must pass.
- **Static analysis: `pylint`.** Must pass.

## Tests

- Run the suite with `uv run pytest`.
- **No slow tests.** A global per-test timeout is enforced via `pytest-timeout`. Tests
  that exceed the timeout fail.
- **Fast subsets** are available through the `justfile`; use `just` recipes to run focused
  or fast subsets during development.
- The **coverage gate must pass** as part of the required checks.

## Commit and Branching Conventions

- **Commits**: follow [Conventional Commits](https://www.conventionalcommits.org/).
  Semantic versioning is derived from commit history.
- **Branches**: keep branches short-lived.
- **No direct pushes to `main`.** `main` is protected; all changes land via pull request.
- **Pull requests** must pass all required checks before merge.

## Code Review

The primary review skill is **thermo-nuclear-code-quality-review**. Install it with:

```
npx skills add https://github.com/cursor/plugins --skill thermo-nuclear-code-quality-review
```

Every non-trivial PR must receive a thermo-nuclear quality review before it is merged.
