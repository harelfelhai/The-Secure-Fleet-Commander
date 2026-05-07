"""
WebSocket connection registries.

GatewayConnectionManager  — one entry per connected Gateway process.
FrontendConnectionManager — one entry per connected browser tab.

Both are singletons accessed at module level.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class GatewayConnectionManager:
    """Tracks one WebSocket per hardware_id."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, hardware_id: str, websocket: WebSocket) -> None:
        # Caller is responsible for websocket.accept() — typically done up front
        # by the route handler so auth can run before registration.
        self._connections[hardware_id] = websocket
        logger.info("Gateway connected: %s", hardware_id)

    def disconnect(self, hardware_id: str) -> None:
        self._connections.pop(hardware_id, None)
        logger.info("Gateway disconnected: %s", hardware_id)

    async def send(self, hardware_id: str, message: str) -> bool:
        """Send a text message to a specific Gateway. Returns False if not connected."""
        ws = self._connections.get(hardware_id)
        if not ws:
            return False
        try:
            await ws.send_text(message)
            return True
        except Exception:
            self.disconnect(hardware_id)
            return False

    def is_connected(self, hardware_id: str) -> bool:
        return hardware_id in self._connections


class FrontendConnectionManager:
    """Broadcast to all connected Frontend clients."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        # Caller is responsible for websocket.accept().
        self._clients.append(websocket)
        logger.info("Frontend client connected (total: %d)", len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients = [c for c in self._clients if c is not websocket]
        logger.info("Frontend client disconnected (total: %d)", len(self._clients))

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for ws in dead:
            self.disconnect(ws)


gateway_manager = GatewayConnectionManager()
frontend_manager = FrontendConnectionManager()
