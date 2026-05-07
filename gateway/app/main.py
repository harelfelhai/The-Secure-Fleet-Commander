"""
Gateway entry point.

Run with:
    python -m app.main
"""

import asyncio
import logging

from app.adapters.simulated import SimulatedDroneAdapter
from app.buffer import OfflineBuffer
from app.config import settings
from app.gateway_client import GatewayClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = settings
    adapter = SimulatedDroneAdapter(
        agent_id=cfg.hardware_id,
        center_lat=cfg.center_lat,
        center_lon=cfg.center_lon,
        orbit_radius_deg=cfg.orbit_radius_deg,
        orbit_period_seconds=cfg.orbit_period_seconds,
        telemetry_hz=cfg.telemetry_hz,
        initial_altitude_m=cfg.initial_altitude_m,
        battery_drain_pct_per_sec=cfg.battery_drain_pct_per_sec,
    )
    await adapter.connect()

    async with OfflineBuffer(
        cfg.offline_buffer_path, cfg.offline_buffer_max_size
    ) as buf:
        client = GatewayClient(cfg, adapter, buf)
        try:
            await client.run()
        finally:
            await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
