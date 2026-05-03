"""
Unit tests for Pydantic message schema validation.
Covers the TELEMETRY frame (primary inbound) and emergency COMMAND schemas.
"""

import pytest
from pydantic import ValidationError

from app.schemas.messages import (
    AckFrame,
    CommandDispatch,
    CommandError,
    CommandSent,
    FrontendCommand,
    TelemetryFrame,
)

VALID_FRAME = {
    "msg_type": "TELEMETRY",
    "schema_version": "1.0",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-05-01T10:00:00Z",
    "latitude": 32.0853,
    "longitude": 34.7818,
    "altitude_m": 120.5,
    "battery_pct": 74.2,
}


def test_valid_telemetry_frame():
    frame = TelemetryFrame.model_validate(VALID_FRAME)
    assert frame.latitude == 32.0853
    assert frame.battery_pct == 74.2


def test_missing_required_field():
    bad = {**VALID_FRAME}
    del bad["battery_pct"]
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_latitude_out_of_range():
    bad = {**VALID_FRAME, "latitude": 91.0}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_longitude_out_of_range():
    bad = {**VALID_FRAME, "longitude": -181.0}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_battery_above_100():
    bad = {**VALID_FRAME, "battery_pct": 101.0}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_battery_below_0():
    bad = {**VALID_FRAME, "battery_pct": -1.0}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_wrong_msg_type():
    bad = {**VALID_FRAME, "msg_type": "COMMAND"}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


def test_wrong_schema_version():
    bad = {**VALID_FRAME, "schema_version": "2.0"}
    with pytest.raises(ValidationError):
        TelemetryFrame.model_validate(bad)


# ── Emergency command schemas ─────────────────────────────────────────────────

VALID_AGENT_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_frontend_command_land():
    cmd = FrontendCommand.model_validate(
        {"msg_type": "COMMAND", "command_type": "LAND", "agent_id": VALID_AGENT_ID}
    )
    assert cmd.command_type == "LAND"


def test_frontend_command_rth():
    cmd = FrontendCommand.model_validate(
        {"msg_type": "COMMAND", "command_type": "RTH", "agent_id": VALID_AGENT_ID}
    )
    assert cmd.command_type == "RTH"


def test_frontend_command_cut_motors():
    cmd = FrontendCommand.model_validate(
        {"msg_type": "COMMAND", "command_type": "CUT_MOTORS", "agent_id": VALID_AGENT_ID}
    )
    assert cmd.command_type == "CUT_MOTORS"


def test_frontend_command_rejects_waypoint():
    with pytest.raises(ValidationError):
        FrontendCommand.model_validate(
            {
                "msg_type": "COMMAND",
                "command_type": "GO_TO_WAYPOINT",
                "agent_id": VALID_AGENT_ID,
            }
        )


def test_command_dispatch_has_no_payload():
    dispatch = CommandDispatch.model_validate(
        {
            "command_id": VALID_AGENT_ID,
            "command_type": "RTH",
            "issued_at": "2026-05-03T10:00:00Z",
        }
    )
    assert dispatch.msg_type == "COMMAND"
    assert not hasattr(dispatch, "payload")


# ── ACK, CommandSent, CommandError schemas ────────────────────────────────────


def test_ack_frame_valid():
    ack = AckFrame.model_validate(
        {
            "msg_type": "ACK",
            "command_id": VALID_AGENT_ID,
            "status": "ACKNOWLEDGED",
            "acked_at": "2026-05-03T10:00:01Z",
        }
    )
    assert ack.status == "ACKNOWLEDGED"


def test_ack_frame_rejects_unknown_status():
    with pytest.raises(ValidationError):
        AckFrame.model_validate(
            {
                "msg_type": "ACK",
                "command_id": VALID_AGENT_ID,
                "status": "OK",
                "acked_at": "2026-05-03T10:00:01Z",
            }
        )


def test_command_sent_schema():
    msg = CommandSent.model_validate(
        {
            "command_id": VALID_AGENT_ID,
            "agent_id": VALID_AGENT_ID,
            "command_type": "LAND",
            "issued_at": "2026-05-03T10:00:00Z",
        }
    )
    assert msg.msg_type == "COMMAND_SENT"
    assert msg.command_type == "LAND"


def test_command_error_schema_with_agent():
    msg = CommandError(agent_id=VALID_AGENT_ID, reason="gateway offline")
    assert msg.msg_type == "COMMAND_ERROR"
    assert msg.agent_id == VALID_AGENT_ID


def test_command_error_schema_without_agent():
    msg = CommandError(reason="invalid command")
    assert msg.agent_id is None
