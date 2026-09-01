# syntax=docker/dockerfile:1
# Multi-stage Alpine image (§13.1): non-root, musllinux wheels for lxml/cryptography,
# no compiler in the final stage.

# Base images digest-pinned (supply-chain: a tag can be repointed upstream with no repo
# diff); Dependabot's docker ecosystem keeps the pins fresh.
FROM ghcr.io/astral-sh/uv:0.12.8@sha256:d1cbaeadc234fe19c0d93daabcf5e98738cd93c6d1dd4918ef6aa30735feb23a AS uv

FROM python:3.14-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# Install dependencies first (cached), then the project itself.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY README.md ./README.md
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable && \
    find /app/.venv -type f \( -name "*.c" -o -name "*.h" \) -delete

FROM python:3.14-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS runtime
# Drop pip from the runtime stage. The venv is built in the builder and copied in whole, and it
# sets include-system-site-packages=false, so nothing at runtime imports the base interpreter's
# site-packages: CMD runs `channel-relay` from /app/.venv and HEALTHCHECK uses wget. Keeping pip
# only ships its vendored tree (pip/_vendor/vendor.txt), which is where Trivy finds
# msgpack GHSA-6v7p-g79w-8964 and setuptools CVE-2025-47273 — neither reachable, both HIGH and
# both blocking the image scan. Globbed on python3.* so a base-image minor bump needs no edit.
# Trade-off: `python -m pip` no longer works inside a running container.
RUN find /usr/local/lib/python3.*/site-packages -maxdepth 1 \
      \( -name "pip" -o -name "pip-*.dist-info" \) -exec rm -rf {} + \
    && ! python -c "import pip" 2>/dev/null
# Drop to a non-root user.
RUN addgroup -g 101 -S relay && adduser -u 100 -S -G relay relay
WORKDIR /app
# Release workflow passes the git-tag version via --build-arg APP_VERSION.
ARG APP_VERSION=0.0.0+unknown
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RELAY_VERSION=${APP_VERSION}
COPY --from=builder --chown=relay:relay /app/.venv /app/.venv
USER 100:101
EXPOSE 8080
# Readiness is gated on config and is the image-level health contract.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1:8080/readiness || exit 1
CMD ["channel-relay"]
