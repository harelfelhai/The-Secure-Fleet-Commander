from fastapi import APIRouter

from app.services.zone_evaluator import get_zones

router = APIRouter(prefix="/api/v1/zones", tags=["zones"])


@router.get("")
async def list_zones() -> dict:
    zones = get_zones()
    return {
        "zones": [
            {"name": z["name"], "type": z["type"], "coordinates": z["coordinates"]}
            for z in zones
        ]
    }
