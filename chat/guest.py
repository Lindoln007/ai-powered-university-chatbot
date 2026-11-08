"""Secure guest sessions.

A guest receives a random secret token when they create their first
conversation. The client sends it back in the ``X-Guest-Token`` header. Only a
SHA-256 hash of the token is stored, so the database never contains usable
guest credentials.
"""

import hashlib
import secrets

GUEST_TOKEN_HEADER = "HTTP_X_GUEST_TOKEN"
MIN_TOKEN_LENGTH = 32
MAX_TOKEN_LENGTH = 128


def generate_guest_token() -> str:
    return secrets.token_urlsafe(32)


def hash_guest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_guest_token(request) -> str | None:
    token = request.META.get(GUEST_TOKEN_HEADER, "").strip()
    if MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH and token.replace("-", "").replace("_", "").isalnum():
        return token
    return None


def get_guest_session_id(request) -> str | None:
    token = get_guest_token(request)
    return hash_guest_token(token) if token else None
