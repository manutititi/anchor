import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from db.client import get_client, close_client
from auth.middleware import AuthMiddleware
from auth.router import router as auth_router
from vault.router import router as vault_router, compat_router as vault_compat_router
from anchors.router import router as anchors_router, compat_router as anchors_compat_router
from endpoints.health import router as health_router
from endpoints.admin import router as admin_router
from endpoints.dashboard import router as dashboard_router
from ui import router as ui_module
from integrations.router import router as integrations_router
from vpn.router import router as vpn_router
from vpn.janitor import start_janitor


templates = Jinja2Templates(directory="/app/templates")
ui_module.set_templates(templates)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_client()  # Verify MongoDB is reachable at startup
    asyncio.create_task(start_janitor())
    yield
    close_client()


app = FastAPI(
    title="Anchor Vault Server",
    version="2.0.0",
    description=(
        "Modular vault and anchor management server. "
        "Supports local and LDAP authentication, service tokens for automation, "
        "AES-256-GCM secret storage with per-secret key derivation (HKDF), "
        "and secret versioning."
    ),
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)

# Core routers
app.include_router(auth_router)
app.include_router(vault_router, prefix="/vault")
app.include_router(anchors_router, prefix="/anchors")
app.include_router(health_router)
app.include_router(admin_router, prefix="/admin")
app.include_router(dashboard_router)
app.include_router(integrations_router, prefix="/integrations")
app.include_router(vpn_router, prefix="/vpn")
app.include_router(ui_module.router, prefix="/ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")

# Backward-compatible aliases (deprecated, kept for existing CLI compatibility)
app.include_router(vault_compat_router)
app.include_router(anchors_compat_router)
