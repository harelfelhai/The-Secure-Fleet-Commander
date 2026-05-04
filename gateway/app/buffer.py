"""
OfflineBuffer — SQLite-backed FIFO queue for telemetry frames.

Frames are pushed when the gateway WS is unavailable and drained FIFO on
reconnect. The buffer is bounded: pushing beyond max_size evicts the oldest
frames to prevent unbounded disk growth during long cloud disconnects.

Usage:
    async with OfflineBuffer("offline_buffer.db", max_size=1000) as buf:
        await buf.push(payload)
        async for payload in buf.drain():
            await ws.send(payload)
"""

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS offline_buffer (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    payload   TEXT    NOT NULL,
    queued_at TEXT    NOT NULL
)
"""


class OfflineBuffer:
    def __init__(self, db_path: str, max_size: int = 1000) -> None:
        self._db_path = db_path
        self._max_size = max_size
        self._db: aiosqlite.Connection | None = None

    # ── Async context manager ──────────────────────────────────────────────────

    async def __aenter__(self) -> "OfflineBuffer":
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.commit()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def push(self, payload: str) -> None:
        """Insert one frame. Trims oldest rows if buffer exceeds max_size."""
        assert self._db, "OfflineBuffer must be used as an async context manager"
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT INTO offline_buffer (payload, queued_at) VALUES (?, ?)",
            (payload, now),
        )
        await self._db.commit()
        await self._trim()

    async def drain(self) -> AsyncGenerator[str, None]:
        """
        Yield buffered payloads in FIFO order, deleting each row immediately
        after yielding. If the caller breaks early, remaining rows stay in the DB.
        """
        assert self._db, "OfflineBuffer must be used as an async context manager"
        async with self._db.execute(
            "SELECT id, payload FROM offline_buffer ORDER BY id ASC"
        ) as cursor:
            async for row_id, payload in cursor:
                yield payload
                await self._db.execute(
                    "DELETE FROM offline_buffer WHERE id = ?", (row_id,)
                )
                await self._db.commit()

    async def size(self) -> int:
        """Return the number of queued frames."""
        assert self._db, "OfflineBuffer must be used as an async context manager"
        async with self._db.execute("SELECT COUNT(*) FROM offline_buffer") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def clear(self) -> None:
        """Delete all rows — used for testing and fresh starts."""
        assert self._db, "OfflineBuffer must be used as an async context manager"
        await self._db.execute("DELETE FROM offline_buffer")
        await self._db.commit()

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _trim(self) -> None:
        """Drop oldest rows so the buffer stays within max_size."""
        current = await self.size()
        excess = current - self._max_size
        if excess > 0:
            await self._db.execute(  # type: ignore[union-attr]
                """
                DELETE FROM offline_buffer
                WHERE id IN (
                    SELECT id FROM offline_buffer ORDER BY id ASC LIMIT ?
                )
                """,
                (excess,),
            )
            await self._db.commit()
            logger.warning(
                "Buffer trimmed %d oldest frame(s) (max_size=%d)",
                excess,
                self._max_size,
            )
