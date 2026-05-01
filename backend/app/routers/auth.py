"""
Dev-only token endpoint — mints a Gateway JWT for a given hardware_id.
This route must be disabled (or protected) in production.
"""

from fastapi import APIRouter

from app.auth.jwt import create_gateway_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/gateway-token")
async def mint_gateway_token(hardware_id: str) -> dict:
    """
    Issue a JWT for the given hardware_id.
    FOR DEVELOPMENT USE ONLY — no authentication required.
    """
    token = create_gateway_token(hardware_id)
    return {"token": token, "hardware_id": hardware_id}
