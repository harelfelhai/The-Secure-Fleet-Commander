"""
Minimal HS256 JWT implementation using stdlib only.
Avoids dependency on python-jose or PyJWT, both of which pull in the
`cryptography` package (which has broken native extensions in some environments).

Produces RFC 7519-compliant compact serialisation tokens.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from app.config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _sign(signing_input: str) -> str:
    sig = hmac.new(
        settings.jwt_secret.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(sig)


def create_gateway_token(hardware_id: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = datetime.now(UTC)
    claims = {
        "sub": hardware_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    payload = _b64url_encode(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}"
    return f"{signing_input}.{_sign(signing_input)}"


def verify_gateway_token(token: str) -> str:
    """Verify signature and expiry. Returns hardware_id or raises ValueError."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"

    # Timing-safe signature check
    expected = _sign(signing_input).encode()
    try:
        actual = _b64url_encode(_b64url_decode(sig_b64)).encode()
    except Exception as exc:
        raise ValueError("Invalid signature encoding") from exc

    if not hmac.compare_digest(expected, actual):
        raise ValueError("Invalid token signature")

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise ValueError("Invalid token payload") from exc

    now = int(datetime.now(UTC).timestamp())
    if claims.get("exp", 0) < now:
        raise ValueError("Token expired")

    hardware_id: str | None = claims.get("sub")
    if not hardware_id:
        raise ValueError("Token missing sub claim")

    return hardware_id
