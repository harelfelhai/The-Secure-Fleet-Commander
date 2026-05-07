import { useCallback } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, useMapEvents } from "react-leaflet";
import { useFleet } from "../context/FleetContext";
import { AgentMarker } from "./AgentMarker";
import { MapFitControl } from "./MapFitControl";
import { NoFlyZones } from "./NoFlyZones";

const DEFAULT_CENTER: [number, number] = [32.0853, 34.7818];
const DEFAULT_ZOOM = 14;

function PlanModeClickHandler() {
  const { dispatch } = useFleet();

  const handleClick = useCallback(
    (e: { latlng: { lat: number; lng: number } }) => {
      dispatch({
        type: "WAYPOINT_ADD",
        payload: {
          id: `wp-${Date.now()}`,
          lat: e.latlng.lat,
          lng: e.latlng.lng,
        },
      });
    },
    [dispatch],
  );

  useMapEvents({ click: handleClick });
  return null;
}

export function FleetMap() {
  const { state } = useFleet();
  const agents = Object.values(state.agents);
  const { replay, planMode, waypoints } = state;

  // Replay trail: points from frame 0 up to and including currentIndex
  const trailPositions: [number, number][] =
    replay.agentId !== null && replay.frames.length > 0
      ? replay.frames
          .slice(0, replay.currentIndex + 1)
          .map((f) => [f.latitude, f.longitude])
      : [];

  const waypointPositions: [number, number][] = waypoints.map((w) => [w.lat, w.lng]);

  return (
    <MapContainer
      className="fleet-map"
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      zoomControl={true}
      // Show crosshair cursor in plan mode
      style={planMode ? { cursor: "crosshair" } : undefined}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <NoFlyZones />
      <MapFitControl />

      {planMode && <PlanModeClickHandler />}

      {agents.map((agent) => (
        <AgentMarker key={agent.agent_id} agent={agent} />
      ))}

      {trailPositions.length > 1 && (
        <Polyline
          positions={trailPositions}
          pathOptions={{ color: "#3b82f6", weight: 2.5, opacity: 0.8 }}
        />
      )}

      {/* Waypoint route line */}
      {waypointPositions.length > 1 && (
        <Polyline
          positions={waypointPositions}
          pathOptions={{ color: "#f59e0b", weight: 2, opacity: 0.9, dashArray: "6 4" }}
        />
      )}

      {/* Waypoint markers */}
      {waypoints.map((wp, idx) => (
        <CircleMarker
          key={wp.id}
          center={[wp.lat, wp.lng]}
          radius={7}
          pathOptions={{ color: "#f59e0b", fillColor: "#fbbf24", fillOpacity: 1, weight: 2 }}
        >
          {/* Label rendered as tooltip alternative via title */}
          <span title={`WP ${idx + 1}`} />
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
