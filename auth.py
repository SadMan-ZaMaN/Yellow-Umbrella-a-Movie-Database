import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from database import get_db

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    # Never fall back to a hardcoded key - anyone who reads the repo could
    # forge an admin token. A random key just means logins reset on restart.
    SECRET_KEY = secrets.token_urlsafe(32)
    print("[auth] JWT_SECRET_KEY is not set, using a temporary random key")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/login", auto_error=False)


# ── Passwords ────────────────────────────────────────────────
# Stored as "pbkdf2_sha256$<iterations>$<salt>$<hash>".
# Older accounts were saved as a bare sha256 hex digest; those still work
# and get upgraded the next time the user logs in.

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(digest.hex(), expected)
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(legacy, stored)


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")


# ── Tokens ───────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_user_token(token: str) -> dict | None:
    """Returns the user inside a login token, or None if the token is bad."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    # password-reset tokens carry a "purpose" and must not work as a login
    if payload.get("sub") is None or payload.get("purpose"):
        return None
    return {
        "userid": int(payload["sub"]),
        "username": payload.get("username"),
        "role": payload.get("role", "user"),
    }


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    user = decode_user_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(token: str | None = Depends(optional_oauth2_scheme)) -> dict | None:
    """Same as get_current_user, but guests get None instead of a 401."""
    if not token:
        return None
    return decode_user_token(token)


# ── Permission checks ────────────────────────────────────────
# The frontend sends user ids in URLs and request bodies, and anyone can
# edit those in the browser. So every route that touches a user's data
# compares that id against the one inside the signed token.

def is_admin(current_user: dict | None) -> bool:
    # Read the role from the database rather than the token, so promoting or
    # demoting someone takes effect now and not whenever their token expires.
    if current_user is None:
        return False
    conn = get_db()
    try:
        rows = conn.run("SELECT role FROM users WHERE userid=:id;", id=current_user["userid"])
    finally:
        conn.close()
    return bool(rows) and rows[0][0] == "admin"


def is_owner_or_admin(current_user: dict | None, user_id: int) -> bool:
    if current_user is None:
        return False
    return current_user["userid"] == user_id or is_admin(current_user)


def check_owner(current_user: dict, user_id: int):
    if current_user["userid"] != user_id:
        raise HTTPException(status_code=403, detail="You can only change your own data")


def check_owner_or_admin(current_user: dict | None, user_id: int):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Please log in first")
    if not is_owner_or_admin(current_user, user_id):
        raise HTTPException(status_code=403, detail="This is private to its owner")


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
