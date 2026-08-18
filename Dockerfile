# syntax=docker/dockerfile:1
# Multi-stage Alpine image (§13.1): non-root, musllinux wheels for lxml/cryptography,
# no compiler in the final stage.

# Base images digest-pinned (supply-chain: a tag can be repointed upstream with no repo
# diff); Dependabot's docker ecosystem keeps the pins fresh.
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

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
