from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth.token import decode_token
from auth.service_token import validate_service_token


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        request.state.groups = []
        request.state.scopes = []
        request.state.token_type = None

        token: str | None = None

        # Bearer token (JWT or service token)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # X-API-Key header (alternative for Kubernetes init containers)
        api_key = request.headers.get("X-API-Key", "")
        if api_key.startswith("anc_"):
            token = api_key

        if token:
            if token.startswith("anc_"):
                result = validate_service_token(token)
                if result:
                    request.state.user = result["name"]
                    request.state.scopes = result["scopes"]
                    request.state.token_type = "service"
                else:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or expired service token"},
                    )
            else:
                try:
                    payload = decode_token(token)
                    request.state.user = payload.get("sub")
                    request.state.groups = payload.get("groups", [])
                    request.state.token_type = "user"
                except HTTPException:
                    return JSONResponse(
                        status_code=401, content={"detail": "Invalid token"}
                    )

        return await call_next(request)


def get_current_user(request: Request) -> str:
    if not request.state.user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user


def get_current_groups(request: Request) -> list[str]:
    return getattr(request.state, "groups", []) or []


def get_current_scopes(request: Request) -> list[str]:
    return getattr(request.state, "scopes", []) or []


def require_group(required: str):
    def checker(request: Request):
        groups = get_current_groups(request)
        if required not in groups:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return True
    return checker


def require_scope(scope: str):
    """For service tokens: require a specific scope. JWT users pass automatically."""
    def checker(request: Request):
        token_type = getattr(request.state, "token_type", None)
        if token_type is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if token_type == "service":
            scopes = get_current_scopes(request)
            if scope not in scopes and "admin" not in scopes:
                raise HTTPException(
                    status_code=403, detail=f"Missing required scope: {scope}"
                )
        return True
    return checker
