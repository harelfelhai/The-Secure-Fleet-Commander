"""
Dev-only token endpoint — mints a Gateway JWT for a given hardware_id.
Disabled at runtime unless `DEBUG=true` (or `settings.debug` is true).
In production, gateway tokens must be provisioned out-of-band.
"""

from fastapi import APIRouter, HTTPException, status

from app.auth.jwt import create_gateway_token
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/gateway-token")
async def mint_gateway_token(hardware_id: str) -> dict:
    """
    Issue a JWT for the given hardware_id.
    DEV-ONLY — returns 403 unless settings.debug is true.
    """
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev-only endpoint disabled. Set DEBUG=true to enable.",
        )
    token = create_gateway_token(hardware_id)
    return {"token": token, "hardware_id": hardware_id}
