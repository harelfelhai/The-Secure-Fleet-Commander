import { MapContainer, Polyline, TileLayer } from "react-leaflet";
import { useFleet } from "../context/FleetContext";
import { AgentMarker } from "./AgentMarker";
import { NoFlyZones } from "./NoFlyZones";

const DEFAULT_CENTER: [number, number] = [32.0853, 34.7818];
const DEFAULT_ZOOM = 14;

export function FleetMap() {
  const { state } = useFleet();
  const agents = Object.values(state.agents);
  const { replay } = state;

  // Replay trail: points from frame 0 up to and including currentIndex
  const trailPositions: [number, number][] =
    replay.agentId !== null && replay.frames.length > 0
      ? replay.frames
          .slice(0, replay.currentIndex + 1)
          .map((f) => [f.latitude, f.longitude])
      : [];

  return (
    <MapContainer
      className="fleet-map"
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <NoFlyZones />

      {agents.map((agent) => (
        <AgentMarker key={agent.agent_id} agent={agent} />
      ))}

      {trailPositions.length > 1 && (
        <Polyline
          positions={trailPositions}
          pathOptions={{ color: "#3b82f6", weight: 2.5, opacity: 0.8 }}
        />
      )}
    </MapContainer>
  );
}
