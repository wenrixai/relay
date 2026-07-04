"""Application entrypoint and factory.

The app factory wires the middleware pipeline (see ``docs/PROJECT.md`` §3.1). This slice
boots the app with health routes; feature stages are added per slice under TDD.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from channel_relay import __version__
from channel_relay.config.loader import load_config
from channel_relay.config.models import RelayConfig
from channel_relay.health import readiness_reasons
from channel_relay.observability.logging import configure_logging
from channel_relay.settings import Settings


def _load_startup_config(settings: Settings) -> RelayConfig | None:
    """Load config on startup.

    Missing file → not ready (returns ``None``); invalid config → raise to abort startup.
    """
    if not Path(settings.config_file).exists():
        logger.warning("Config file not found at {}; relay not ready", settings.config_file)
        return None
    return load_config(settings.config_file)


def create_app(config: RelayConfig | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config: an explicit config (used in tests). When omitted, the lifespan loads it
            from ``Settings.config_file``.

    ``server_header=False`` is enforced at the server level (uvicorn) per §9.1.
    """
    settings = Settings()
    configure_logging(debug=settings.debug)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Load config once on startup unless one was injected (invalid → abort).
        if application.state.config is None:
            application.state.config = _load_startup_config(settings)
        yield

    application = FastAPI(
        title="Wenrix Channel Relay",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.config = config

    @application.get("/liveness")
    async def liveness() -> dict[str, str]:
        """Liveness probe: the process is up."""
        return {"status": "alive"}

    @application.get("/readiness")
    async def readiness() -> JSONResponse:
        """Readiness probe: ready only when config has loaded; reasons otherwise (§13.5)."""
        reasons = readiness_reasons(application.state.config)
        if reasons:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reasons": reasons},
            )
        return JSONResponse(status_code=200, content={"status": "ready"})

    return application


app = create_app()


def cli() -> None:
    """Console entrypoint: run the relay with uvicorn (``server_header=False``)."""
    uvicorn.run(
        "channel_relay.main:app",
        host="0.0.0.0",  # relay binds all interfaces inside its container
        port=Settings().port,
        server_header=False,
    )
