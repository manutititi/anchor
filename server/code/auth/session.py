from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import JWTError, jwt
from datetime import datetime, timedelta
from code.core.utils import now_tz, now_tz_ss
import os

# Clave secreta JWT (usar una variable de entorno en producción)
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60


def create_token(username: str, groups: list[str]) -> str:
    expire = now_tz_ss() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "groups": groups,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = decode_token(token)
                request.state.user = payload.get("sub")
                request.state.groups = payload.get("groups", [])
            except HTTPException:
                return JSONResponse(status_code=401, content={"detail": "Invalid token"})
        else:
            request.state.user = None
            request.state.groups = []

        return await call_next(request)


def get_current_user(request: Request) -> str:
    if not request.state.user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user


def get_current_groups(request: Request) -> list[str]:
    return request.state.groups or []


def require_group(required: str):
    def checker(request: Request):
        groups = get_current_groups(request)
        if required not in groups:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return True
    return checker
