from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates: Jinja2Templates | None = None


def set_templates(t: Jinja2Templates):
    global templates
    templates = t


@router.get("", response_class=HTMLResponse)
@router.get("/login", response_class=HTMLResponse)
def ui_login(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/setup", response_class=HTMLResponse)
def ui_setup(request: Request):
    return templates.TemplateResponse(request, "setup.html")


@router.get("/anchors", response_class=HTMLResponse)
def ui_anchors(request: Request):
    return templates.TemplateResponse(request, "anchors.html")


@router.get("/secrets", response_class=HTMLResponse)
def ui_secrets(request: Request):
    return templates.TemplateResponse(request, "secrets.html")


@router.get("/users", response_class=HTMLResponse)
def ui_users(request: Request):
    return templates.TemplateResponse(request, "users.html")


@router.get("/logs", response_class=HTMLResponse)
def ui_logs(request: Request):
    return templates.TemplateResponse(request, "logs.html")


@router.get("/integrations", response_class=HTMLResponse)
def ui_integrations(request: Request):
    return templates.TemplateResponse(request, "integrations.html")


@router.get("/wireguard", response_class=HTMLResponse)
def ui_wireguard(request: Request):
    return templates.TemplateResponse(request, "wireguard.html")
