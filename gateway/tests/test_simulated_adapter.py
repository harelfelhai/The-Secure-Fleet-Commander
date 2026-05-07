"""
Unit tests for SimulatedDroneAdapter.
asyncio.sleep is patched to zero so tests run instantly.
"""

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.simulated import DroneMode, SimulatedDroneAdapter
from app.schemas import CommandDispatch, TelemetryFrame

AGENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

CENTER_LAT = 32.0853
CENTER_LON = 34.7818
RADIUS = 0.005
PERIOD = 30.0
HZ = 5.0
ALT = 50.0
DRAIN = 0.5  # %/s


def make_adapter(**kwargs) -> SimulatedDroneAdapter:
    defaults = dict(
        agent_id=AGENT_ID,
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        orbit_radius_deg=RADIUS,
        orbit_period_seconds=PERIOD,
        telemetry_hz=HZ,
        initial_altitude_m=ALT,
        battery_drain_pct_per_sec=DRAIN,
    )
    return SimulatedDroneAdapter(**{**defaults, **kwargs})


def make_command(command_type: str) -> CommandDispatch:
    return CommandDispatch(
        msg_type="COMMAND",
        command_id="cmd-001",
        command_type=command_type,
        issued_at=datetime.now(UTC),
    )


# ── read_telemetry produces valid frames ──────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_telemetry_frame_validates_schema(mock_sleep):
    adapter = make_adapter()
    await adapter.connect()
    frame = await adapter.read_telemetry()

    assert isinstance(frame, TelemetryFrame)
    assert frame.agent_id == AGENT_ID
    assert -90 <= frame.latitude <= 90
    assert -180 <= frame.longitude <= 180
    assert 0 <= frame.battery_pct <= 100
    assert frame.altitude_m >= 0


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_position_advances_each_frame(mock_sleep):
    adapter = make_adapter()
    await adapter.connect()
    f1 = await adapter.read_telemetry()
    f2 = await adapter.read_telemetry()

    # Position must change between frames (angle advances)
    assert f1.latitude != f2.latitude or f1.longitude != f2.longitude


# ── Orbit geometry ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_one_full_orbit_returns_near_start(mock_sleep):
    """After period_seconds * hz frames the drone is back where it started."""
    adapter = make_adapter()
    await adapter.connect()

    frames_per_orbit = int(PERIOD * HZ)
    first = await adapter.read_telemetry()
    for _ in range(frames_per_orbit - 1):
        await adapter.read_telemetry()
    last = await adapter.read_telemetry()

    # Allow 1 m tolerance (≈ 0.00001 deg) for floating-point accumulation
    assert abs(last.latitude - first.latitude) < 0.0001
    assert abs(last.longitude - first.longitude) < 0.0001


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_orbit_radius_respected(mock_sleep):
    """Every frame's distance from center must be within ≈ radius."""
    adapter = make_adapter()
    await adapter.connect()
    for _ in range(10):
        frame = await adapter.read_telemetry()
        dlat = frame.latitude - CENTER_LAT
        dlon = frame.longitude - CENTER_LON
        dist = math.sqrt(dlat**2 + dlon**2)
        assert abs(dist - RADIUS) < 0.001, f"dist={dist:.5f} expected≈{RADIUS}"


# ── Battery drain ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_battery_drains_at_configured_rate(mock_sleep):
    adapter = make_adapter(battery_drain_pct_per_sec=DRAIN, telemetry_hz=HZ)
    await adapter.connect()
    f1 = await adapter.read_telemetry()
    f2 = await adapter.read_telemetry()

    expected_drain_per_frame = DRAIN / HZ
    actual_drain = f1.battery_pct - f2.battery_pct
    assert abs(actual_drain - expected_drain_per_frame) < 0.001


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_battery_never_goes_below_zero(mock_sleep):
    adapter = make_adapter(battery_drain_pct_per_sec=100.0)  # instant drain
    await adapter.connect()
    for _ in range(20):
        frame = await adapter.read_telemetry()
    assert frame.battery_pct == 0.0


# ── LAND command ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_land_command_sets_landing_mode(mock_sleep):
    adapter = make_adapter()
    await adapter.connect()
    await adapter.send_command(make_command("LAND"))
    assert adapter.mode == DroneMode.LANDING


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_land_command_reduces_altitude_to_zero(mock_sleep):
    adapter = make_adapter(initial_altitude_m=5.0, telemetry_hz=HZ)
    await adapter.connect()
    await adapter.send_command(make_command("LAND"))

    # With LAND_DESCENT_RATE=5 m/s and 5 Hz → 1 m per frame → 5 frames to land
    for _ in range(10):
        frame = await adapter.read_telemetry()
    assert frame.altitude_m == 0.0
    assert adapter.mode == DroneMode.LANDED


# ── CUT_MOTORS command ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_cut_motors_drops_altitude_immediately(mock_sleep):
    adapter = make_adapter()
    await adapter.connect()
    await adapter.send_command(make_command("CUT_MOTORS"))
    frame = await adapter.read_telemetry()
    assert frame.altitude_m == 0.0
    assert adapter.mode == DroneMode.LANDED


# ── RTH command ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_rth_command_sets_rth_mode(mock_sleep):
    adapter = make_adapter()
    await adapter.connect()
    await adapter.send_command(make_command("RTH"))
    assert adapter.mode == DroneMode.RTH


@pytest.mark.asyncio
@patch("app.adapters.simulated.asyncio.sleep", new_callable=AsyncMock)
async def test_rth_drone_converges_toward_center(mock_sleep):
    """After RTH, successive frames should be closer to center than before."""
    adapter = make_adapter()
    await adapter.connect()
    # Advance a few frames so the drone is away from center
    for _ in range(5):
        await adapter.read_telemetry()

    await adapter.send_command(make_command("RTH"))
    frame_before = await adapter.read_telemetry()
    dist_before = math.sqrt(
        (frame_before.latitude - CENTER_LAT) ** 2
        + (frame_before.longitude - CENTER_LON) ** 2
    )

    for _ in range(10):
        frame_after = await adapter.read_telemetry()
    dist_after = math.sqrt(
        (frame_after.latitude - CENTER_LAT) ** 2
        + (frame_after.longitude - CENTER_LON) ** 2
    )

    assert dist_after < dist_before
