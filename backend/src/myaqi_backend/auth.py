from __future__ import annotations

import base64
import hashlib
import hmac
import time


class AuthenticationError(Exception):
    pass


def derive_device_secret(master_key: str, device_id: str, key_version: int = 1) -> bytes:
    context = f"myaqi/device-key/v{key_version}/{device_id}".encode()
    return hmac.new(master_key.encode(), context, hashlib.sha256).digest()


def encode_device_secret(secret: bytes) -> str:
    return base64.urlsafe_b64encode(secret).decode().rstrip("=")


def decode_device_secret(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_request(timestamp: str, method: str, path: str, body: bytes) -> bytes:
    return f"{timestamp}\n{method.upper()}\n{path}\n{body_sha256(body)}".encode()


def sign_request(secret: bytes, timestamp: str, method: str, path: str, body: bytes) -> str:
    digest = hmac.new(
        secret,
        canonical_request(timestamp, method, path, body),
        hashlib.sha256,
    ).hexdigest()
    return f"v1={digest}"


def verify_request_signature(
    *,
    secret: bytes,
    timestamp: str | None,
    signature: str | None,
    method: str,
    path: str,
    body: bytes,
    max_clock_skew_seconds: int,
    now: int | None = None,
) -> None:
    if not timestamp or not signature:
        raise AuthenticationError("Missing device authentication headers")

    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise AuthenticationError("Invalid device timestamp") from exc

    current_time = int(time.time()) if now is None else now
    if abs(current_time - request_time) > max_clock_skew_seconds:
        raise AuthenticationError("Device timestamp is outside the allowed clock window")

    expected = sign_request(secret, timestamp, method, path, body)
    if not hmac.compare_digest(expected, signature):
        raise AuthenticationError("Invalid device signature")
