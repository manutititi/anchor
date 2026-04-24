import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
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
from vpn.knock import start_knock_listener

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="/app/templates")
ui_module.set_templates(templates)


def _seed_wireguard_integration():
    """
    If no wireguard integration config exists in MongoDB, create one from env vars
    so the server works out of the box without manual UI setup.
    """
    from integrations.store import get_config, save_config
    from config import settings

    if get_config("wireguard") is not None:
        return

    routes = [r.strip() for r in settings.WG_ROUTES.split(",") if r.strip()]

    # Build endpoint as host:port — if WG_SERVER_ENDPOINT already has a port, use it;
    # otherwise append WG_SERVERPORT.
    endpoint = settings.WG_SERVER_ENDPOINT
    if endpoint and ":" not in endpoint:
        endpoint = f"{endpoint}:{settings.WG_SERVERPORT}"

    config = {
        "sidecar_url": settings.WG_SIDECAR_URL,
        "api_key": settings.WG_API_KEY,
        "subnet": settings.WG_SUBNET,
        "server_endpoint": endpoint,
        "lease_hours": settings.WG_LEASE_HOURS,
        "enabled": True,
        "knock_port": settings.VPN_KNOCK_PORT,
        "server_vpn_uid": 1,
        "routes": routes,
        "dns": [],
    }
    save_config("wireguard", config, ["api_key"], "system")
    logger.info("Seeded wireguard integration config from env vars")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_client()  # Verify MongoDB is reachable at startup

    # Seed WireGuard integration from env if not yet configured
    _seed_wireguard_integration()

    asyncio.create_task(start_janitor())

    # Initialize SPA v2 server keypair
    from vpn.spa import init_server_keypair
    from config import settings
    init_server_keypair(settings.SPA_PRIVKEY_B64)

    # Start SPA knock listener.
    # Uses VPN_KNOCK_PORT env var if set, otherwise falls back to the
    # WireGuard integration config from MongoDB. Starts whenever a port
    # is configured — does not require is_enabled() to pass.
    knock_task = None
    try:
        wg_cfg: dict = {}
        try:
            from integrations.wireguard.provider import WireGuardProvider
            wg_cfg = WireGuardProvider()._get_config() or {}
        except Exception:
            pass

        knock_port = settings.VPN_KNOCK_PORT or int(wg_cfg.get("knock_port", 0) or 0)
        if knock_port > 0:
            subnet = wg_cfg.get("subnet", "10.13.13.0/24")
            knock_task = asyncio.create_task(
                start_knock_listener(settings.VPN_KNOCK_HOST, knock_port, subnet)
            )
            logger.info("SPA knock listener task created (port=%d)", knock_port)
        else:
            logger.info("SPA knock listener disabled: no knock_port configured")
    except Exception:
        logger.exception("Failed to start SPA knock listener")

    yield

    # Graceful shutdown: cancel knock listener
    if knock_task and not knock_task.done():
        knock_task.cancel()
        try:
            await knock_task
        except asyncio.CancelledError:
            pass

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

app.mount("/static", StaticFiles(directory="/app/static"), name="static")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")

# Backward-compatible aliases (deprecated, kept for existing CLI compatibility)
app.include_router(vault_compat_router)
app.include_router(anchors_compat_router)
