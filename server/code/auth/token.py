from datetime import timedelta
from jose import JWTError, jwt
from fastapi import HTTPException
from config import settings
from core.utils import now_tz_ss


def create_token(username: str, groups: list[str], token_type: str = "user") -> str:
    expire = now_tz_ss() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "groups": groups,
        "token_type": token_type,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
