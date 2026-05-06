import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { useFleet } from "../context/FleetContext";

function fitAgents(map: ReturnType<typeof useMap>, agents: { latitude: number; longitude: number }[]) {
  if (agents.length === 0) return;
  if (agents.length === 1) {
    map.setView([agents[0].latitude, agents[0].longitude], map.getZoom());
    return;
  }
  const lats = agents.map((a) => a.latitude);
  const lons = agents.map((a) => a.longitude);
  map.fitBounds(
    [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ],
    { padding: [60, 60], maxZoom: 16 },
  );
}

// Rendered inside MapContainer so useMap() works.
export function MapFitControl() {
  const map = useMap();
  const { state } = useFleet();
  const hasAutoFit = useRef(false);

  const agents = Object.values(state.agents);

  // Auto-fit once when the first agents arrive.
  useEffect(() => {
    if (hasAutoFit.current || agents.length === 0) return;
    hasAutoFit.current = true;
    fitAgents(map, agents);
  }, [map, agents]);

  if (agents.length === 0) return null;

  return (
    <div className="leaflet-bottom leaflet-left" style={{ marginBottom: "8px", marginLeft: "8px" }}>
      <div className="leaflet-control">
        <button
          onClick={() => fitAgents(map, agents)}
          title="Fit to fleet"
          className="flex h-8 items-center gap-1.5 rounded-lg border border-gray-600 bg-gray-900/90 px-2.5 text-xs font-medium text-gray-200 shadow hover:bg-gray-800"
        >
          ⊙ Fleet
        </button>
      </div>
    </div>
  );
}
