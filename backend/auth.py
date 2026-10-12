from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import settings
from models import TokenData
import database as db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Payload of a valid access token (untyped or type "access"), else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") not in (None, "access"):
        return None  # a 2FA challenge token (or any other typed token) is not an access token
    if payload.get("sub") is None:
        return None
    return payload

def decode_token(token: str) -> Optional[str]:
    payload = decode_access_token(token)
    return payload["sub"] if payload else None

def create_mfa_token(username: str, user_id: str, token_version: int = 0) -> str:
    """Short-lived token proving the password step of a 2FA login succeeded."""
    return create_access_token(
        data={"sub": username, "user_id": user_id, "type": "mfa", "ver": token_version},
        expires_delta=timedelta(minutes=settings.MFA_TOKEN_EXPIRE_MINUTES)
    )

def decode_mfa_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
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
    if not user or payload.get("ver", 0) != user.get("token_version", 0):
        raise credentials_exception
    return payload["sub"]
