"""
Unit tests for Pydantic message schema validation.
Covers the TELEMETRY frame — the primary inbound message.
"""

import pytest
from pydantic import ValidationError

from app.schemas.messages import TelemetryFrame


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
