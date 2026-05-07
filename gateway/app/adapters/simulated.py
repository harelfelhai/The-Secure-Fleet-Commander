"""
SimulatedDroneAdapter — generates synthetic telemetry for a drone flying a
circular orbit, with realistic battery drain and state-based command reactions.

Flight model
------------
Position traces a circle around (center_lat, center_lon):
    lat(t) = center_lat + radius * sin(angle)
    lon(t) = center_lon + radius * cos(angle)
    angle  += angular_step per frame   (angular_step = 2π / (period * hz))

Altitude is held constant at initial_altitude_m with ±0.5 m Gaussian noise,
unless a LAND / CUT_MOTORS command changes the target altitude.

Battery drains linearly at battery_drain_pct_per_sec.

Command reactions
-----------------
LAND        — target altitude drops at LAND_DESCENT_RATE_M_S until 0; position holds.
RTH         — drone steers back toward center; lands on arrival.
CUT_MOTORS  — altitude snaps to 0 on the very next frame.
"""

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto

from app.adapters.base import AbstractDeviceAdapter
from app.schemas import CommandDispatch, TelemetryFrame

logger = logging.getLogger(__name__)

LAND_DESCENT_RATE_M_S = 5.0  # metres per second during controlled landing
RTH_STEER_DEG_PER_FRAME = 0.0005  # how aggressively the drone steers toward home


class DroneMode(Enum):
    ORBIT = auto()
    LANDING = auto()
    LANDED = auto()
    RTH = auto()
    CUT = auto()


@dataclass
class DroneState:
    angle: float = 0.0  # radians around the orbit
    altitude_m: float = 50.0
    battery_pct: float = 100.0
    mode: DroneMode = DroneMode.ORBIT
    # RTH: current position converges to center each frame
    lat: float = 0.0
    lon: float = 0.0


class SimulatedDroneAdapter(AbstractDeviceAdapter):
    def __init__(
        self,
        agent_id: str,
        center_lat: float,
        center_lon: float,
        orbit_radius_deg: float,
        orbit_period_seconds: float,
        telemetry_hz: float,
        initial_altitude_m: float,
        battery_drain_pct_per_sec: float,
    ) -> None:
        self._agent_id = agent_id
        self._center_lat = center_lat
        self._center_lon = center_lon
        self._radius = orbit_radius_deg
        self._angular_step = (2 * math.pi) / (orbit_period_seconds * telemetry_hz)
        self._frame_interval = 1.0 / telemetry_hz
        self._battery_drain_per_frame = battery_drain_pct_per_sec / telemetry_hz

        self._state = DroneState(
            altitude_m=initial_altitude_m,
            lat=center_lat + orbit_radius_deg,  # start at 3-o'clock on the orbit
            lon=center_lon,
        )

    # ── AbstractDeviceAdapter ──────────────────────────────────────────────────

    async def connect(self) -> None:
        logger.info(
            "SimulatedDroneAdapter connected: agent_id=%s center=(%.4f,%.4f)",
            self._agent_id,
            self._center_lat,
            self._center_lon,
        )

    async def read_telemetry(self) -> TelemetryFrame:
        await asyncio.sleep(self._frame_interval)
        self._advance_state()
        return TelemetryFrame(
            agent_id=self._agent_id,
            timestamp=datetime.now(UTC),
            latitude=round(self._state.lat, 6),
            longitude=round(self._state.lon, 6),
            altitude_m=round(self._state.altitude_m, 1),
            battery_pct=round(self._state.battery_pct, 2),
        )

    async def send_command(self, command: CommandDispatch) -> None:
        logger.info(
            "Command received: type=%s id=%s", command.command_type, command.command_id
        )
        if command.command_type == "LAND":
            self._state.mode = DroneMode.LANDING
        elif command.command_type == "RTH":
            self._state.mode = DroneMode.RTH
        elif command.command_type == "CUT_MOTORS":
            self._state.mode = DroneMode.CUT

    async def disconnect(self) -> None:
        logger.info("SimulatedDroneAdapter disconnected")

    # ── Internal state machine ─────────────────────────────────────────────────

    def _advance_state(self) -> None:
        """Advance position, altitude, and battery by one frame tick."""
        self._drain_battery()

        mode = self._state.mode

        if mode == DroneMode.ORBIT:
            self._orbit_step()

        elif mode == DroneMode.LANDING:
            # Hold horizontal position — only altitude changes during descent
            self._state.altitude_m += random.gauss(0, 0.05)
            drop = LAND_DESCENT_RATE_M_S * self._frame_interval
            self._state.altitude_m = max(0.0, self._state.altitude_m - drop)
            if self._state.altitude_m == 0.0:
                self._state.mode = DroneMode.LANDED
                logger.info("Drone landed")

        elif mode == DroneMode.LANDED:
            pass  # stationary on ground

        elif mode == DroneMode.RTH:
            self._rth_step()

        elif mode == DroneMode.CUT:
            self._state.altitude_m = 0.0
            self._state.mode = DroneMode.LANDED
            logger.warning("Motors cut — drone dropped to ground")

    def _orbit_step(self) -> None:
        self._state.angle += self._angular_step
        self._state.lat = self._center_lat + self._radius * math.sin(self._state.angle)
        self._state.lon = self._center_lon + self._radius * math.cos(self._state.angle)
        # small altitude noise to make telemetry feel realistic
        self._state.altitude_m += random.gauss(0, 0.1)
        self._state.altitude_m = max(0.0, self._state.altitude_m)

    def _rth_step(self) -> None:
        dlat = self._center_lat - self._state.lat
        dlon = self._center_lon - self._state.lon
        dist = math.sqrt(dlat**2 + dlon**2)

        if dist <= RTH_STEER_DEG_PER_FRAME:
            # arrived at home — begin landing
            self._state.lat = self._center_lat
            self._state.lon = self._center_lon
            self._state.mode = DroneMode.LANDING
            logger.info("RTH: reached home, beginning landing")
        else:
            scale = RTH_STEER_DEG_PER_FRAME / dist
            self._state.lat += dlat * scale
            self._state.lon += dlon * scale

    def _drain_battery(self) -> None:
        self._state.battery_pct = max(
            0.0, self._state.battery_pct - self._battery_drain_per_frame
        )

    # ── Inspection helpers (used in tests) ────────────────────────────────────

    @property
    def state(self) -> DroneState:
        return self._state

    @property
    def mode(self) -> DroneMode:
        return self._state.mode
