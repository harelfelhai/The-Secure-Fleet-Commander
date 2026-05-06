"""
Dev-only token endpoint — mints a Gateway JWT for a given hardware_id.
Enabled by default; set ALLOW_GATEWAY_TOKEN_ENDPOINT=false in production
to disable it (or place the backend behind a firewall that blocks this path).
"""

from fastapi import APIRouter, HTTPException, status

from app.auth.jwt import create_gateway_token
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/gateway-token")
async def mint_gateway_token(hardware_id: str) -> dict:
    """
    Issue a JWT for the given hardware_id.
    Disable in production with ALLOW_GATEWAY_TOKEN_ENDPOINT=false.
    """
    if not settings.allow_gateway_token_endpoint:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gateway token endpoint is disabled on this server.",
        )
    token = create_gateway_token(hardware_id)
    return {"token": token, "hardware_id": hardware_id}
