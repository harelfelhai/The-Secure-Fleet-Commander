import { useEffect, useReducer, type ReactNode } from "react";
import { FleetContext } from "../context/FleetContext";
import { fleetReducer, initialState } from "../context/fleet.reducer";
import { useFleetSocket } from "../hooks/useFleetSocket";
import type { TrailPoint, ZonePolygon } from "../types/fleet";

interface TrailResponse {
  latitude: number;
  longitude: number;
  altitude_m: number;
  battery_pct: number;
  recorded_at: string;
}

interface ZoneApiResponse {
  zones: Array<{
    name: string;
    type: string;
    coordinates: [number, number][]; // [lon, lat] (Shapely order)
  }>;
}

export function RealFleetProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(fleetReducer, initialState);
  const { sendCommand } = useFleetSocket(dispatch);

  // Fetch zones once on mount — they're static for the session.
  useEffect(() => {
    fetch("/api/v1/zones")
      .then((r) => r.json() as Promise<ZoneApiResponse>)
      .then((data) => {
        const zones: ZonePolygon[] = data.zones
          .filter((z) => z.type === "POLYGON" && z.coordinates.length >= 3)
          // Backend stores [lon, lat]; Leaflet wants [lat, lon].
          .map((z) => ({
            name: z.name,
            latlngs: z.coordinates.map(
              ([lon, lat]) => [lat, lon] as [number, number],
            ),
          }));
        dispatch({ type: "ZONES_LOADED", payload: zones });
      })
      .catch((err) => console.warn("Failed to load zones:", err));
  }, []);

  const loadTrail = async (agentId: string): Promise<void> => {
    try {
      const res = await fetch(`/api/v1/agents/${agentId}/breadcrumbs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = (await res.json()) as TrailResponse[];
      const frames: TrailPoint[] = raw.map((r) => ({
        latitude: r.latitude,
        longitude: r.longitude,
        altitude_m: r.altitude_m,
        battery_pct: r.battery_pct,
        recorded_at: r.recorded_at,
      }));
      dispatch({ type: "REPLAY_LOADED", payload: { agentId, frames } });
    } catch (err) {
      console.error("Failed to load trail:", err);
    }
  };

  return (
    <FleetContext.Provider value={{ state, dispatch, loadTrail, sendCommand }}>
      {children}
    </FleetContext.Provider>
  );
}
