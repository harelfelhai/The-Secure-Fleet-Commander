"""
GatewayClient — connects the SimulatedDroneAdapter to the Fleet Commander backend.

Lifecycle per connection attempt:
  1. Acquire JWT via POST /gateways/auth
  2. Open WebSocket → validate READY handshake
  3. Run three concurrent tasks under asyncio.TaskGroup:
       A. Live producer  — reads adapter telemetry → ws.send()
                           saves to buffer on ConnectionClosed
       B. Buffer drainer — replays OfflineBuffer frames with is_backfill=True
                           yields to the event loop after each send so Task C
                           (command receiver) stays responsive
       C. Command receiver — ws.recv() → adapter.send_command() → ACK
  4. On any task failure → cancel siblings → exponential backoff → retry from step 1

Concurrent send safety:
  Tasks A and B both call ws.send(). A asyncio.Lock (_send_lock) serialises them
  so websockets never sees interleaved writes.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.adapters.base import AbstractDeviceAdapter
from app.buffer import OfflineBuffer
from app.config import SimulatorSettings
from app.schemas import AckFrame, CommandDispatch, ReadyMessage

logger = logging.getLogger(__name__)

_READY_TIMEOUT = 10.0  # seconds to wait for READY handshake after WS open


class GatewayClient:
    def __init__(
        self,
        config: SimulatorSettings,
        adapter: AbstractDeviceAdapter,
        buffer: OfflineBuffer,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._buffer = buffer
        self._send_lock = asyncio.Lock()

    # ── Public entry point ─────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run forever, reconnecting with exponential backoff on failures."""
        backoff = 1.0
        while True:
            try:
                token = await self._authenticate()
                await self._run_session(token)
                # _run_session returns normally only if cancelled — reset backoff
                backoff = 1.0
            except asyncio.CancelledError:
                logger.info("GatewayClient cancelled — shutting down")
                raise
            except Exception as exc:
                logger.warning(
                    "Connection failed (%s), retrying in %.1fs", type(exc).__name__, backoff
                )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._config.reconnect_backoff_max_seconds)

    # ── Authentication ─────────────────────────────────────────────────────────

    async def _authenticate(self) -> str:
        url = f"{self._config.backend_api_url}/gateways/auth"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"hardware_id": self._config.hardware_id})
            resp.raise_for_status()
            return resp.json()["token"]

    # ── Session (single WS connection) ────────────────────────────────────────

    async def _run_session(self, token: str) -> None:
        ws_url = (
            f"{self._config.backend_ws_url}/ws/gateway/{self._config.hardware_id}"
        )
        async with websockets.connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await self._handshake(ws)
            logger.info("Gateway session open for hardware_id=%s", self._config.hardware_id)

            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._task_live_producer(ws))
                    tg.create_task(self._task_buffer_drainer(ws))
                    tg.create_task(self._task_command_receiver(ws))
            except* ConnectionClosed as eg:
                logger.warning("WS connection closed: %s", eg.exceptions[0])
                raise eg.exceptions[0]
            except* Exception as eg:
                logger.error("Session task failed: %s", eg.exceptions[0])
                raise eg.exceptions[0]

    async def _handshake(self, ws: Any) -> None:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=_READY_TIMEOUT)
        except TimeoutError as exc:
            raise ConnectionError("READY handshake timed out") from exc
        msg = json.loads(raw)
        if msg.get("msg_type") != "READY":
            raise ConnectionError(f"Expected READY, got: {msg.get('msg_type')}")
        ready = ReadyMessage.model_validate(msg)
        logger.info("READY received: agent_id=%s session_id=%s", ready.agent_id, ready.session_id)

    # ── Task A: Live telemetry producer ───────────────────────────────────────

    async def _task_live_producer(self, ws: Any) -> None:
        while True:
            frame = await self._adapter.read_telemetry()
            payload = frame.model_dump_json()
            try:
                async with self._send_lock:
                    await ws.send(payload)
            except ConnectionClosed:
                # Save unsent frame so it drains on the next reconnect
                await self._buffer.push(payload)
                raise

    # ── Task B: Offline buffer drainer ────────────────────────────────────────

    async def _task_buffer_drainer(self, ws: Any) -> None:
        """
        Replay buffered frames with is_backfill=True, then exit.

        `await asyncio.sleep(0)` after each send yields to the event loop so
        Task C (command receiver) can process incoming commands without waiting
        for the entire backlog to flush.
        """
        async for raw_payload in self._buffer.drain():
            frame_dict = json.loads(raw_payload)
            frame_dict["is_backfill"] = True
            async with self._send_lock:
                await ws.send(json.dumps(frame_dict))
            await asyncio.sleep(0)  # keep Task C responsive during large backfills

    # ── Task C: Command receiver ───────────────────────────────────────────────

    async def _task_command_receiver(self, ws: Any) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("msg_type") != "COMMAND":
                    logger.warning("Unexpected message type: %s", msg.get("msg_type"))
                    continue
                command = CommandDispatch.model_validate(msg)
                await self._adapter.send_command(command)
                ack = AckFrame(
                    command_id=command.command_id,
                    status="ACKNOWLEDGED",
                    acked_at=datetime.now(UTC),
                )
                async with self._send_lock:
                    await ws.send(ack.model_dump_json())
            except Exception:
                logger.error("Error handling command", exc_info=True)
