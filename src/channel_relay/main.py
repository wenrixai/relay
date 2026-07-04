"""Application entrypoint and factory.

The app factory wires the middleware pipeline (see ``docs/PROJECT.md`` §3.1). This
scaffold boots an empty app with health routes only; feature stages are added per
slice under TDD.
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from channel_relay import __version__


def create_app() -> FastAPI:
    """Build the FastAPI application.

    ``server_header=False`` is enforced at the server level (uvicorn) per §9.1; the
    factory keeps the app itself free of a ``Server`` header surface.
    """
    application = FastAPI(
        title="Wenrix Channel Relay",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.get("/liveness")
    async def liveness() -> dict[str, str]:
        """Liveness probe: the process is up."""
        return {"status": "alive"}

    @application.get("/readiness")
    async def readiness() -> dict[str, str]:
        """Readiness probe. Reasons are populated once config/rules load (T1.5)."""
        return {"status": "ready"}

    return application


app = create_app()


def cli() -> None:
    """Console entrypoint: run the relay with uvicorn (``server_header=False``)."""
    uvicorn.run(
        "channel_relay.main:app",
        host="0.0.0.0",  # relay binds all interfaces inside its container
        port=8080,
        server_header=False,
    )
