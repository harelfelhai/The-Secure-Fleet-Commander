"""
Unit tests for the No-Fly Zone Evaluator.
These tests are pure — no I/O, no database.
"""

import pytest

from app.services import zone_evaluator


@pytest.fixture(autouse=True)
def load_test_zones(tmp_path):
    """Load a minimal zones.json into the evaluator for every test."""
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        """{
          "zones": [
            {
              "name": "Test Zone Alpha",
              "type": "POLYGON",
              "coordinates": [
                [34.77, 32.08],
                [34.79, 32.08],
                [34.79, 32.10],
                [34.77, 32.10],
                [34.77, 32.08]
              ]
            }
          ]
        }"""
    )
    zone_evaluator.load_zones(str(zones_file))
    yield
    zone_evaluator._zones = []


def test_point_inside_zone():
    violated, name = zone_evaluator.evaluate(longitude=34.78, latitude=32.09)
    assert violated is True
    assert name == "Test Zone Alpha"


def test_point_outside_zone():
    violated, name = zone_evaluator.evaluate(longitude=35.00, latitude=33.00)
    assert violated is False
    assert name is None


def test_point_on_boundary_is_not_inside():
    # Shapely .contains() returns False for boundary points (strict interior)
    violated, _ = zone_evaluator.evaluate(longitude=34.77, latitude=32.08)
    assert violated is False


def test_no_zones_loaded():
    zone_evaluator._zones = []
    violated, name = zone_evaluator.evaluate(longitude=34.78, latitude=32.09)
    assert violated is False
    assert name is None


def test_missing_zones_file():
    zone_evaluator.load_zones("/nonexistent/path/zones.json")
    assert zone_evaluator._zones == []


def test_get_zones_returns_metadata_only():
    zones = zone_evaluator.get_zones()
    assert len(zones) == 1
    assert zones[0]["name"] == "Test Zone Alpha"
    assert "polygon" not in zones[0]
