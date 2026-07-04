# syntax=docker/dockerfile:1
# Multi-stage Alpine image (§13.1): non-root, musllinux wheels for lxml/cryptography,
# no compiler in the final stage.

FROM ghcr.io/astral-sh/uv:0.5.11 AS uv

FROM python:3.13-alpine AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
# Install dependencies first (cached), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./README.md
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-alpine AS runtime
# Drop to a non-root user.
RUN addgroup -S relay && adduser -S -G relay relay
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=relay:relay /app/.venv /app/.venv
COPY --from=builder --chown=relay:relay /app/src /app/src
USER relay
EXPOSE 8080
# Liveness = process up; readiness is gated on config and used by the orchestrator.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1:8080/liveness || exit 1
CMD ["channel-relay"]
