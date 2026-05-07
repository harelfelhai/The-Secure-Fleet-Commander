"""
Unit tests for GatewayClient.

All tests use mocks — no real WS or network required.
The buffer uses ":memory:" SQLite so tests leave no files.
"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.buffer import OfflineBuffer
from app.config import SimulatorSettings
from app.gateway_client import GatewayClient
from app.schemas import CommandDispatch, TelemetryFrame

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_config(**kwargs) -> SimulatorSettings:
    defaults = dict(
        backend_ws_url="ws://testhost",
        backend_api_url="http://testhost",
        hardware_id="test-drone",
        reconnect_backoff_max_seconds=30.0,
        telemetry_hz=5.0,
        center_lat=0.0,
        center_lon=0.0,
        orbit_radius_deg=0.005,
        orbit_period_seconds=30.0,
        initial_altitude_m=50.0,
        battery_drain_pct_per_sec=0.5,
        offline_buffer_path=":memory:",
        offline_buffer_max_size=100,
    )
    defaults.update(kwargs)
    return SimulatorSettings(**defaults)


def make_frame(**kwargs) -> TelemetryFrame:
    defaults = dict(
        agent_id="test-drone",
        timestamp=datetime.now(UTC),
        latitude=0.0,
        longitude=0.0,
        altitude_m=50.0,
        battery_pct=80.0,
    )
    defaults.update(kwargs)
    return TelemetryFrame(**defaults)


def make_command() -> CommandDispatch:
    return CommandDispatch(
        msg_type="COMMAND",
        command_id="cmd-001",
        command_type="LAND",
        issued_at=datetime.now(UTC),
    )


# ── Backoff ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backoff_doubles_on_repeated_failure():
    """run() should double the sleep duration on each consecutive failure."""
    config = make_config()
    adapter = MagicMock()
    sleeps = []

    async with OfflineBuffer(":memory:", 100) as buf:
        client = GatewayClient(config, adapter, buf)
        call_count = 0

        async def fake_authenticate():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError
            raise ConnectionError("refused")

        async def fake_sleep(t):
            sleeps.append(t)

        client._authenticate = fake_authenticate
        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await client.run()

    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
async def test_backoff_capped_at_max():
    """Backoff must not exceed reconnect_backoff_max_seconds."""
    config = make_config(reconnect_backoff_max_seconds=5.0)
    adapter = MagicMock()
    sleeps = []

    async with OfflineBuffer(":memory:", 100) as buf:
        client = GatewayClient(config, adapter, buf)
        call_count = 0

        async def fake_authenticate():
            nonlocal call_count
            call_count += 1
            if call_count >= 6:
                raise asyncio.CancelledError
            raise ConnectionError("refused")

        async def fake_sleep(t):
            sleeps.append(t)

        client._authenticate = fake_authenticate
        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await client.run()

    assert all(s <= 5.0 for s in sleeps)
    assert sleeps[-1] == 5.0


# ── Buffer drainer — is_backfill flag ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_drainer_sets_is_backfill_true():
    """Frames replayed from the buffer must carry is_backfill=True when sent."""
    config = make_config()
    adapter = MagicMock()
    sent_payloads = []

    async with OfflineBuffer(":memory:", 100) as buf:
        # Pre-load two frames into the buffer
        for i in range(2):
            frame = make_frame(latitude=float(i))
            await buf.push(frame.model_dump_json())

        client = GatewayClient(config, adapter, buf)
        ws = MagicMock()

        async def fake_send(payload):
            sent_payloads.append(json.loads(payload))

        ws.send = fake_send
        await client._task_buffer_drainer(ws)

    assert len(sent_payloads) == 2
    assert all(p["is_backfill"] is True for p in sent_payloads)


@pytest.mark.asyncio
async def test_drainer_preserves_original_fields():
    """Backfill frames must keep all original telemetry fields intact."""
    config = make_config()
    adapter = MagicMock()
    sent_payloads = []

    async with OfflineBuffer(":memory:", 100) as buf:
        frame = make_frame(latitude=1.23, longitude=4.56, battery_pct=42.0)
        await buf.push(frame.model_dump_json())

        client = GatewayClient(config, adapter, buf)
        ws = MagicMock()

        async def fake_send(payload):
            sent_payloads.append(json.loads(payload))

        ws.send = fake_send
        await client._task_buffer_drainer(ws)

    p = sent_payloads[0]
    assert p["latitude"] == 1.23
    assert p["longitude"] == 4.56
    assert p["battery_pct"] == 42.0


# ── Live producer — buffer on disconnect ─────────────────────────────────────


@pytest.mark.asyncio
async def test_live_frame_buffered_on_ws_disconnect():
    """When ws.send raises ConnectionClosed, the frame must land in the buffer."""
    from websockets.exceptions import ConnectionClosed as WsClosed

    config = make_config()
    frame = make_frame()

    adapter = MagicMock()
    adapter.read_telemetry = AsyncMock(return_value=frame)

    async with OfflineBuffer(":memory:", 100) as buf:
        client = GatewayClient(config, adapter, buf)
        ws = MagicMock()

        # Simulate connection drop on first send
        ws.send = AsyncMock(side_effect=WsClosed(None, None))

        with pytest.raises(WsClosed):
            await client._task_live_producer(ws)

        assert await buf.size() == 1
        drained = [p async for p in buf.drain()]
        saved = json.loads(drained[0])
        assert saved["latitude"] == frame.latitude


# ── Command receiver — dispatch + ACK ────────────────────────────────────────


@pytest.mark.asyncio
async def test_command_dispatched_and_ack_sent():
    """Received COMMAND must call adapter.send_command and send an ACK back."""
    config = make_config()
    command = make_command()
    command_json = json.dumps(
        {
            "msg_type": "COMMAND",
            "command_id": command.command_id,
            "command_type": command.command_type,
            "issued_at": command.issued_at.isoformat(),
        }
    )

    adapter = MagicMock()
    adapter.send_command = AsyncMock()

    ack_payloads = []

    async def fake_send(payload):
        ack_payloads.append(json.loads(payload))

    # ws.__aiter__ yields one command then stops
    async def fake_aiter():
        yield command_json

    ws = MagicMock()
    ws.__aiter__ = lambda _: fake_aiter()
    ws.send = fake_send

    async with OfflineBuffer(":memory:", 100) as buf:
        client = GatewayClient(config, adapter, buf)
        await client._task_command_receiver(ws)

    adapter.send_command.assert_awaited_once()
    dispatched: CommandDispatch = adapter.send_command.call_args[0][0]
    assert dispatched.command_id == command.command_id

    assert len(ack_payloads) == 1
    assert ack_payloads[0]["msg_type"] == "ACK"
    assert ack_payloads[0]["command_id"] == command.command_id
    assert ack_payloads[0]["status"] == "ACKNOWLEDGED"


# ── send_lock — concurrent sends serialised ───────────────────────────────────


@pytest.mark.asyncio
async def test_send_lock_prevents_concurrent_sends():
    """Tasks A and B must never call ws.send concurrently."""
    config = make_config()
    adapter = MagicMock()

    concurrent_count = 0
    max_concurrent = 0
    send_order = []

    async with OfflineBuffer(":memory:", 100) as buf:
        # Seed the buffer with one frame
        frame = make_frame()
        await buf.push(frame.model_dump_json())

        client = GatewayClient(config, adapter, buf)
        ws = MagicMock()

        async def fake_send(payload):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            send_order.append(json.loads(payload).get("is_backfill", False))
            await asyncio.sleep(0)  # allow other tasks to run
            concurrent_count -= 1

        ws.send = fake_send

        # Run drainer (B) and a single-shot live send (A) concurrently
        async def one_live_send():
            async with client._send_lock:
                await ws.send(frame.model_dump_json())

        await asyncio.gather(
            client._task_buffer_drainer(ws),
            one_live_send(),
        )

    # Lock must prevent simultaneous ws.send calls
    assert max_concurrent == 1
