"""
No-Fly Zone Evaluator.

Pure evaluation logic: given a point (lon, lat) and the loaded zone list,
returns (is_violation: bool, zone_name: str | None).

Coordinate convention: GeoJSON order — (longitude, latitude).
Zones are loaded once at startup and held in module-level state.
"""

import json
import logging
from pathlib import Path

from shapely.geometry import Point, Polygon

logger = logging.getLogger(__name__)

# Module-level zone cache: list of {"name": str, "type": str, "polygon": Polygon, "coordinates": list}
_zones: list[dict] = []


def load_zones(config_path: str) -> None:
    """Load and parse zones.json into shapely Polygons. Called once at startup."""
    global _zones
    path = Path(config_path)
    if not path.exists():
        logger.warning("zones.json not found at %s — no-fly zone evaluation disabled", config_path)
        _zones = []
        return

    with path.open() as f:
        raw = json.load(f)

    _zones = []
    for zone in raw.get("zones", []):
        # coordinates are [[lon, lat], ...] (GeoJSON order)
        polygon = Polygon([(c[0], c[1]) for c in zone["coordinates"]])
        _zones.append({
            "name": zone["name"],
            "type": zone["type"],
            "polygon": polygon,
            "coordinates": zone["coordinates"],
        })

    logger.info("Loaded %d no-fly zones", len(_zones))


def get_zones() -> list[dict]:
    return [{"name": z["name"], "type": z["type"], "coordinates": z["coordinates"]} for z in _zones]


def evaluate(longitude: float, latitude: float) -> tuple[bool, str | None]:
    """
    Check whether (longitude, latitude) falls inside any configured no-fly zone.

    Returns (True, zone_name) on first match, (False, None) if no violation.
    """
    point = Point(longitude, latitude)
    for zone in _zones:
        if zone["polygon"].contains(point):
            return True, zone["name"]
    return False, None
