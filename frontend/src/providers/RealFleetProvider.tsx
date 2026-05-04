import { useReducer, type ReactNode } from "react";
import { FleetContext } from "../context/FleetContext";
import { fleetReducer, initialState } from "../context/fleet.reducer";
import { useFleetSocket } from "../hooks/useFleetSocket";
import type { TrailPoint } from "../types/fleet";

interface TrailResponse {
  latitude: number;
  longitude: number;
  altitude_m: number;
  battery_pct: number;
  recorded_at: string;
}

export function RealFleetProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(fleetReducer, initialState);

  useFleetSocket(dispatch);

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
    <FleetContext.Provider value={{ state, dispatch, loadTrail }}>
      {children}
    </FleetContext.Provider>
  );
}
