from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db.client import get_client
from config import settings

router = APIRouter()


@router.get("/health", tags=["health"])
def health():
    """Liveness probe — checks MongoDB connectivity."""
    try:
        get_client().admin.command("ping")
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": f"Database connection failed: {e}"},
        )


@router.get("/health/ready", tags=["health"])
def health_ready():
    """Readiness probe — checks MongoDB and required configuration."""
    errors = []

    try:
        get_client().admin.command("ping")
    except Exception as e:
        errors.append(f"MongoDB: {e}")

    required_vars = ("MONGO_URI", "MONGO_DB", "JWT_SECRET", "VAULT_MASTER_KEY")
    for var in required_vars:
        if not getattr(settings, var, None):
            errors.append(f"Missing required config: {var}")

    if errors:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "errors": errors},
        )
    return {"status": "ready"}
