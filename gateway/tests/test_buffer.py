"""
Unit tests for OfflineBuffer.
Uses an in-memory SQLite DB (":memory:") so tests are fast and leave no files.
"""

import pytest

from app.buffer import OfflineBuffer


def make_buffer(max_size: int = 10) -> OfflineBuffer:
    return OfflineBuffer(":memory:", max_size=max_size)


async def drain_all(buf: OfflineBuffer) -> list[str]:
    return [payload async for payload in buf.drain()]


# ── size / push ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_increases_size():
    async with make_buffer() as buf:
        assert await buf.size() == 0
        await buf.push("frame-1")
        assert await buf.size() == 1
        await buf.push("frame-2")
        assert await buf.size() == 2


@pytest.mark.asyncio
async def test_size_zero_on_empty_buffer():
    async with make_buffer() as buf:
        assert await buf.size() == 0


# ── drain ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drain_yields_fifo_order():
    async with make_buffer() as buf:
        for i in range(5):
            await buf.push(f"frame-{i}")

        result = await drain_all(buf)

    assert result == ["frame-0", "frame-1", "frame-2", "frame-3", "frame-4"]


@pytest.mark.asyncio
async def test_drain_deletes_rows():
    async with make_buffer() as buf:
        await buf.push("frame-1")
        await buf.push("frame-2")

        await drain_all(buf)

        assert await buf.size() == 0


@pytest.mark.asyncio
async def test_drain_on_empty_yields_nothing():
    async with make_buffer() as buf:
        result = await drain_all(buf)

    assert result == []


@pytest.mark.asyncio
async def test_partial_drain_leaves_remainder():
    """
    Breaking mid-drain gives at-least-once delivery:
    - The row that was *yielded and then break'd* stays in the buffer
      because its DELETE runs only after the yield resumes — which never
      happens on a break.
    - Only rows whose yield fully resumed (i.e. the caller continued to the
      next iteration) are deleted.

    So after draining 2 items and breaking: frame-0 is deleted (resumed),
    frame-1 is still in DB (break prevented its DELETE), frames 2-4 untouched.
    Remaining = 4.
    """
    async with make_buffer() as buf:
        for i in range(5):
            await buf.push(f"frame-{i}")

        count = 0
        async for _ in buf.drain():
            count += 1
            if count == 2:
                break

        remaining = await buf.size()

    # frame-0 deleted; frame-1 through frame-4 remain (4 rows)
    assert remaining == 4


# ── trim / overflow ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trim_on_overflow_keeps_max_size():
    async with make_buffer(max_size=3) as buf:
        for i in range(5):
            await buf.push(f"frame-{i}")

        assert await buf.size() == 3


@pytest.mark.asyncio
async def test_trim_keeps_newest_frames():
    async with make_buffer(max_size=3) as buf:
        for i in range(5):
            await buf.push(f"frame-{i}")

        result = await drain_all(buf)

    # Oldest 2 (frame-0, frame-1) should have been evicted
    assert result == ["frame-2", "frame-3", "frame-4"]


@pytest.mark.asyncio
async def test_push_at_exact_max_size_does_not_trim():
    async with make_buffer(max_size=3) as buf:
        for i in range(3):
            await buf.push(f"frame-{i}")

        assert await buf.size() == 3
        result = await drain_all(buf)

    assert result == ["frame-0", "frame-1", "frame-2"]


# ── clear ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_empties_buffer():
    async with make_buffer() as buf:
        await buf.push("frame-1")
        await buf.push("frame-2")
        await buf.clear()

        assert await buf.size() == 0
