"""
Unit tests for CommandService.
DB and GatewayConnectionManager are fully mocked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Agent, CommandLog
from app.schemas.messages import FrontendCommand
from app.services.command_service import CommandService

AGENT_ID = uuid.uuid4()
AGENT = Agent(
    id=AGENT_ID,
    hardware_id="drone-001",
    display_name="Drone 001",
    link_status="LINKED",
)

VALID_CMD = FrontendCommand.model_validate(
    {"msg_type": "COMMAND", "command_type": "LAND", "agent_id": str(AGENT_ID)}
)


def make_db(agent: Agent | None = AGENT, extra_execute_results: list | None = None):
    """
    Returns a mock AsyncSession where the first execute() returns `agent`
    and subsequent executes return items from extra_execute_results.
    """
    db = MagicMock()
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=begin_ctx)
    db.add = MagicMock()

    agent_result = MagicMock()
    agent_result.scalar_one_or_none = MagicMock(return_value=agent)

    side_effects = [agent_result]
    for item in extra_execute_results or []:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=item)
        side_effects.append(r)

    db.execute = AsyncMock(side_effect=side_effects)
    return db


def make_gw(connected: bool = True, send_ok: bool = True) -> MagicMock:
    gw = MagicMock()
    gw.is_connected = MagicMock(return_value=connected)
    gw.send = AsyncMock(return_value=send_ok)
    return gw


@pytest.mark.asyncio
async def test_dispatch_success_returns_log():
    db = make_db()
    gw = make_gw()
    svc = CommandService(db=db, gw_manager=gw)

    log, error = await svc.dispatch(VALID_CMD)

    assert error == ""
    assert log is not None
    assert log.command_type == "LAND"
    assert log.status == "SENT"
    assert log.payload == {}
    gw.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_success_sends_correct_command_type():
    for cmd_type in ("LAND", "RTH", "CUT_MOTORS"):
        db = make_db()
        gw = make_gw()
        svc = CommandService(db=db, gw_manager=gw)
        cmd = FrontendCommand.model_validate(
            {"msg_type": "COMMAND", "command_type": cmd_type, "agent_id": str(AGENT_ID)}
        )
        log, error = await svc.dispatch(cmd)
        assert error == ""
        assert log.command_type == cmd_type


@pytest.mark.asyncio
async def test_dispatch_unknown_agent():
    db = make_db(agent=None)
    gw = make_gw()
    svc = CommandService(db=db, gw_manager=gw)

    log, error = await svc.dispatch(VALID_CMD)

    assert log is None
    assert error == "agent not found"
    gw.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_gateway_offline_returns_error():
    mock_log = MagicMock(spec=CommandLog)
    db = make_db(extra_execute_results=[mock_log])
    gw = make_gw(connected=False)
    svc = CommandService(db=db, gw_manager=gw)

    log, error = await svc.dispatch(VALID_CMD)

    assert error == "gateway offline"
    assert log.status == "FAILED"
    gw.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_gateway_send_fails_returns_error():
    mock_log = MagicMock(spec=CommandLog)
    db = make_db(extra_execute_results=[mock_log])
    gw = make_gw(connected=True, send_ok=False)
    svc = CommandService(db=db, gw_manager=gw)

    log, error = await svc.dispatch(VALID_CMD)

    assert error == "delivery failed"
    assert log.status == "FAILED"


@pytest.mark.asyncio
async def test_dispatch_writes_command_log_to_db():
    db = make_db()
    gw = make_gw()
    svc = CommandService(db=db, gw_manager=gw)

    await svc.dispatch(VALID_CMD)

    db.add.assert_called_once()
    added: CommandLog = db.add.call_args[0][0]
    assert isinstance(added, CommandLog)
    assert added.agent_id == AGENT_ID
    assert added.status == "SENT"
