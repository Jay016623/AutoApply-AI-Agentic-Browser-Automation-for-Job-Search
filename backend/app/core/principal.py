"""Authenticated principal token model and verification helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.core.auth import Role


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: Role
    exp: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_segment: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_segment.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def issue_principal_token(
    *,
    user_id: str,
    tenant_id: str,
    role: Role,
    secret: str,
    ttl_seconds: int,
) -> str:
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role.value,
        "exp": int(time.time()) + ttl_seconds,
        "ver": 1,
    }
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_segment, secret)
    return f"{payload_segment}.{signature}"


def parse_principal_token(token: str, secret: str) -> Principal:
    try:
        payload_segment, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_format") from exc

    expected = _sign(payload_segment, secret)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_signature")

    try:
        payload_raw = _b64url_decode(payload_segment)
        payload = json.loads(payload_raw.decode("utf-8"))
        role = Role(payload["role"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_payload") from exc

    exp = int(payload.get("exp", 0))
    if exp <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")

    user_id = str(payload.get("user_id", "")).strip()
    tenant_id = str(payload.get("tenant_id", "")).strip()
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_subject")

    return Principal(user_id=user_id, tenant_id=tenant_id, role=role, exp=exp)
