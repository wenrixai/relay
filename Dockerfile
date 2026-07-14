# syntax=docker/dockerfile:1
# Multi-stage Alpine image (§13.1): non-root, musllinux wheels for lxml/cryptography,
# no compiler in the final stage.

FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

FROM python:3.14-alpine AS builder
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

FROM python:3.14-alpine AS runtime
# Drop to a non-root user.
RUN addgroup -g 101 -S relay && adduser -u 100 -S -G relay relay
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=relay:relay /app/.venv /app/.venv
USER 100:101
EXPOSE 8080
# Readiness is gated on config and is the image-level health contract.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1:8080/readiness || exit 1
CMD ["channel-relay"]
