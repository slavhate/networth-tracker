import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import settings
from models import TokenData
import database as db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def has_control_characters(text: str) -> bool:
    """Whether text holds a control character (NUL, newline, escape, ...), which no username or password needs.
    bcrypt refuses a NUL outright, so such a password must be turned away before it gets there."""
    return any(unicodedata.category(ch) == "Cc" for ch in text)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Slow (bcrypt): async routes run it in a worker thread so it doesn't hold up the event loop."""
    if has_control_characters(plain_password):
        return False
    return pwd_context.verify(plain_password[:72], hashed_password)

def get_password_hash(password: str) -> str:
    """Slow (bcrypt): async routes run it in a worker thread so it doesn't hold up the event loop."""
    return pwd_context.hash(password[:72])

@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A hash of a random password nobody knows: a login for an unknown username is checked against it, so it
    takes as long as one for a real user and the response time doesn't tell whether the username exists."""
    return get_password_hash(secrets.token_urlsafe(32))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def _decode(token: str) -> Optional[dict]:
    """The payload of a token signed with our key and algorithm and not expired, else None. The algorithm list
    is fixed, so a token can't pick its own (e.g. "none")."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                          options={"require": ["exp"]})
    except jwt.PyJWTError:
        return None

def decode_access_token(token: str) -> Optional[dict]:
    """Payload of a valid access token (untyped or type "access"), else None."""
    payload = _decode(token)
    if payload is None:
        return None
    if payload.get("type") not in (None, "access"):
        return None  # a 2FA challenge token (or any other typed token) is not an access token
    if payload.get("sub") is None:
        return None
    return payload

def decode_token(token: str) -> Optional[str]:
    payload = decode_access_token(token)
    return payload["sub"] if payload else None

def token_version_of(user: dict) -> int:
    """The user's current token version; missing or null counts as 0."""
    return int(user.get("token_version") or 0)

def create_mfa_token(username: str, user_id: str, token_version: int = 0) -> str:
    """Short-lived token proving the password step of a 2FA login succeeded."""
    return create_access_token(
        data={"sub": username, "user_id": user_id, "type": "mfa", "ver": token_version},
        expires_delta=timedelta(minutes=settings.MFA_TOKEN_EXPIRE_MINUTES)
    )

def decode_mfa_token(token: str) -> Optional[dict]:
    payload = _decode(token)
    if payload is None:
        return None
    if payload.get("type") != "mfa" or not payload.get("sub") or not payload.get("user_id"):
        return None
    return payload

async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    # Tokens carry the user's token_version ("ver", missing = 0); a password change bumps it,
    # which revokes every token issued before the change.
    user = db.get_user_by_username(payload["sub"])
    if not user or payload.get("ver", 0) != token_version_of(user):
        raise credentials_exception
    return payload["sub"]
