"""
Unit tests for FleetBroadcaster link-status tracking.

Covers:
  - mark_cloud_lost: marks all agents for a gateway as CLOUD_LOST
  - mark_link_status RADIO_LOST: marks single agent, status→STALE
  - mark_link_status LINKED: re-marks single agent, status→ONLINE
  - mark_link_status unknown agent: logs warning, no crash
  - update_agent with gateway_hardware_id registers the mapping
"""

from unittest.mock import AsyncMock, MagicMock

from app.services.broadcaster import FleetBroadcaster


def make_broadcaster() -> FleetBroadcaster:
    frontend = MagicMock()
    frontend.broadcast = AsyncMock()
    return FleetBroadcaster(frontend_manager=frontend)


_FRAME = {
    "latitude": 32.0,
    "longitude": 34.0,
    "altitude_m": 50.0,
    "battery_pct": 80.0,
    "last_seen_at": "2026-05-01T10:00:00+00:00",
}


def test_mark_cloud_lost_sets_agents_stale():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME, gateway_hardware_id="gw-001")
    bc.update_agent("agent-2", "Bravo", _FRAME, gateway_hardware_id="gw-001")

    bc.mark_cloud_lost("gw-001")

    assert bc._fleet["agent-1"].status == "STALE"
    assert bc._fleet["agent-1"].link_status == "CLOUD_LOST"
    assert bc._fleet["agent-2"].status == "STALE"
    assert bc._fleet["agent-2"].link_status == "CLOUD_LOST"


def test_mark_cloud_lost_removes_gateway_registry():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME, gateway_hardware_id="gw-001")
    bc.mark_cloud_lost("gw-001")

    assert "gw-001" not in bc._gateway_agents


def test_mark_cloud_lost_only_affects_own_gateway():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME, gateway_hardware_id="gw-001")
    bc.update_agent("agent-2", "Bravo", _FRAME, gateway_hardware_id="gw-002")

    bc.mark_cloud_lost("gw-001")

    assert bc._fleet["agent-1"].link_status == "CLOUD_LOST"
    assert bc._fleet["agent-2"].link_status == "LINKED"
    assert bc._fleet["agent-2"].status == "ONLINE"


def test_mark_link_status_radio_lost():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME, gateway_hardware_id="gw-001")

    bc.mark_link_status("agent-1", "RADIO_LOST")

    assert bc._fleet["agent-1"].link_status == "RADIO_LOST"
    assert bc._fleet["agent-1"].status == "STALE"


def test_mark_link_status_linked_restores_online():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME, gateway_hardware_id="gw-001")
    bc.mark_link_status("agent-1", "RADIO_LOST")
    bc.mark_link_status("agent-1", "LINKED")

    assert bc._fleet["agent-1"].link_status == "LINKED"
    assert bc._fleet["agent-1"].status == "ONLINE"


def test_mark_link_status_unknown_agent_no_crash():
    bc = make_broadcaster()
    bc.mark_link_status("nonexistent", "RADIO_LOST")  # must not raise


def test_update_agent_without_gateway_does_not_register():
    bc = make_broadcaster()
    bc.update_agent("agent-1", "Alpha", _FRAME)  # no gateway_hardware_id

    assert bc._gateway_agents == {}
