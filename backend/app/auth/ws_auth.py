from fastapi import WebSocket

from app.auth.jwt import verify_gateway_token


async def authenticate_gateway_ws(websocket: WebSocket, hardware_id: str) -> bool:
    """
    Validate the JWT query param on a Gateway WebSocket connection.

    Must be called AFTER websocket.accept(). Returns True on success;
    closes the socket with 4401 and returns False on any auth failure.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="missing token")
        return False

    try:
        token_hw_id = verify_gateway_token(token)
    except ValueError:
        await websocket.close(code=4401, reason="invalid token")
        return False

    if token_hw_id != hardware_id:
        await websocket.close(code=4401, reason="hardware_id mismatch")
        return False

    return True
