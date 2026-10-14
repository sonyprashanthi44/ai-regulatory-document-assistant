from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(token_url="/api/auth/login")

# In-memory users only (portfolio demo — no DB)
_users: dict[str, dict] = {}


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class UserOut(BaseModel):
    email: EmailStr
    full_name: str = ""


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_user(data: UserCreate) -> UserOut:
    email = data.email.lower()
    if email in _users:
        raise HTTPException(status_code=400, detail="Email already registered")
    _users[email] = {
        "email": email,
        "full_name": data.full_name,
        "hashed_password": hash_password(data.password),
    }
    return UserOut(email=email, full_name=data.full_name)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = _users.get(email.lower())
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(email: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": email, "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserOut:
    settings = get_settings()
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if not email:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = _users.get(email.lower())
    if not user:
        raise cred_exc
    return UserOut(email=user["email"], full_name=user["full_name"])
