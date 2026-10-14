from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

ITERATIONS = 210_000
SESSIONS: dict[str, "AuthSession"] = {}


@dataclass
class AuthSession:
    user_id: int
    username: str
    role: str
    expires_at: float


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_token(user_id: int, username: str, role: str, ttl_hours: int = 12) -> str:
    token = secrets.token_urlsafe(36)
    SESSIONS[token] = AuthSession(
        user_id=user_id,
        username=username,
        role=role,
        expires_at=time.time() + ttl_hours * 3600,
    )
    return token


def get_session(token: str) -> Optional[AuthSession]:
    session = SESSIONS.get(token)
    if not session:
        return None
    if session.expires_at < time.time():
        SESSIONS.pop(token, None)
        return None
    return session


def revoke_token(token: str) -> None:
    SESSIONS.pop(token, None)
