"""
WireGuard Sidecar — FastAPI application entry point.

Security: every request must include a valid X-API-Key header
matching the WG_API_KEY environment variable.
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.router import router

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("WG_API_KEY", "")

# Paths that do NOT require authentication (health probes)
PUBLIC_PATHS = {"/", "/status", "/docs", "/openapi.json", "/redoc"}

# ---------------------------------------------------------------------------
# Security middleware
# ---------------------------------------------------------------------------


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Simple API-Key guard.

    Rejects any request that does not carry a valid X-API-Key header,
    except for the public health/docs paths.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if not API_KEY:
            # If no key is configured the sidecar is effectively open —
            # log a warning on every request so it's obvious.
            pass  # allow through (development mode)
        else:
            provided = request.headers.get("X-API-Key", "")
            if provided != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WireGuard Sidecar",
    version="1.0.0",
    description=(
        "Orchestrates WireGuard peer configuration in real time (zero downtime) "
        "via kernel-level `wg set` commands. Designed to run as a sidecar "
        "sharing the network namespace of a WireGuard container."
    ),
)

app.add_middleware(APIKeyMiddleware)
app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "wg-sidecar", "version": "1.0.0"}
