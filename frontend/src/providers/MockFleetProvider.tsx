/**
 * MockFleetProvider — drives the Fleet state machine with simulated data.
 *
 * Two drones orbit different centres.  Battery drains at a fixed rate; a
 * LOW_BATTERY alert fires once per drone when battery crosses below 20 %.
 * All frames are recorded so loadTrail() can return the full session history.
 *
 * Toggle with VITE_USE_MOCK=true (or ?mock=true in the URL).
 */

import { useEffect, useReducer, useRef, type ReactNode } from "react";
import { FleetContext } from "../context/FleetContext";
import { fleetReducer, initialState } from "../context/fleet.reducer";
import type {
  AgentState,
  CommandType,
  TrailPoint,
  ZonePolygon,
} from "../types/fleet";

// ── Simulation config ─────────────────────────────────────────────────────────

type SimMode = "ORBIT" | "LANDING" | "LANDED" | "RTH" | "CUT";

interface AgentSim {
  id: string;
  displayName: string;
  centerLat: number;
  centerLon: number;
  radius: number;
  angularStep: number; // radians per tick
  angle: number; // current angle
  battery: number; // current %
  drainPerTick: number; // % per tick
  startedAt: string; // ISO-8601
  lowBatteryFired: boolean;
  mode: SimMode;
  altitude: number;
  lat: number;
  lon: number;
}

const TICK_MS = 500; // simulation rate: 2 Hz
const LOW_BATTERY_PCT = 20;
const LAND_DESCENT_M_PER_TICK = 5; // 10 m/s descent
const RTH_STEP_DEG = 0.0003;

const INITIAL_SIMS: AgentSim[] = [
  {
    id: "mock-drone-001",
    displayName: "Alpha-1",
    centerLat: 32.0853,
    centerLon: 34.7818,
    radius: 0.005,
    angularStep: (2 * Math.PI) / (30 * (1000 / TICK_MS)), // full orbit in 30 s
    angle: 0,
    battery: 100,
    drainPerTick: 0.25, // ≈ 0.5 %/s → LOW_BATTERY after ~3.3 min
    startedAt: new Date().toISOString(),
    lowBatteryFired: false,
    mode: "ORBIT",
    altitude: 50,
    lat: 32.0853,
    lon: 34.7818 + 0.005,
  },
  {
    id: "mock-drone-002",
    displayName: "Bravo-2",
    centerLat: 32.093,
    centerLon: 34.795,
    radius: 0.003,
    angularStep: (2 * Math.PI) / (45 * (1000 / TICK_MS)), // full orbit in 45 s
    angle: Math.PI, // start on opposite side
    battery: 55, // already partway drained → enters yellow quickly
    drainPerTick: 0.2,
    startedAt: new Date(Date.now() - 90_000).toISOString(), // 90 s ago
    lowBatteryFired: false,
    mode: "ORBIT",
    altitude: 40,
    lat: 32.093,
    lon: 34.795 - 0.003,
  },
];

// Demo zones — one near Alpha-1's orbit so the drone enters it during a demo.
const MOCK_ZONES: ZonePolygon[] = [
  {
    name: "Restricted Airspace Alpha",
    latlngs: [
      [32.08, 34.77],
      [32.08, 34.79],
      [32.1, 34.79],
      [32.1, 34.77],
    ],
  },
  {
    name: "Airport Exclusion Zone",
    latlngs: [
      [32.0, 34.88],
      [32.0, 34.92],
      [32.02, 34.92],
      [32.02, 34.88],
    ],
  },
];

// ── Provider ──────────────────────────────────────────────────────────────────

export function MockFleetProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(fleetReducer, initialState);

  // Mutable simulation state — lives in a ref to avoid triggering re-renders
  const simsRef = useRef<AgentSim[]>(structuredClone(INITIAL_SIMS));

  // Per-agent history: agent_id → recorded frames
  const historyRef = useRef<Map<string, TrailPoint[]>>(
    new Map(INITIAL_SIMS.map((s) => [s.id, []])),
  );

  useEffect(() => {
    dispatch({ type: "WS_STATUS", payload: "OPEN" });
    dispatch({ type: "ZONES_LOADED", payload: MOCK_ZONES });

    const tick = () => {
      const sims = simsRef.current;
      const agents: AgentState[] = [];

      for (const sim of sims) {
        advanceSim(sim);

        const now = new Date().toISOString();

        // Record history for trail replay
        const frame: TrailPoint = {
          latitude: parseFloat(sim.lat.toFixed(6)),
          longitude: parseFloat(sim.lon.toFixed(6)),
          altitude_m: parseFloat(sim.altitude.toFixed(1)),
          battery_pct: parseFloat(sim.battery.toFixed(2)),
          recorded_at: now,
        };
        historyRef.current.get(sim.id)?.push(frame);

        agents.push({
          agent_id: sim.id,
          display_name: sim.displayName,
          device_type: "DRONE",
          latitude: frame.latitude,
          longitude: frame.longitude,
          altitude_m: frame.altitude_m,
          battery_pct: frame.battery_pct,
          last_seen_at: now,
          mission_start_at: sim.startedAt,
          status: "ONLINE",
          link_status: "LINKED",
        });

        // Fire LOW_BATTERY alert once when battery drops at or below threshold
        if (!sim.lowBatteryFired && sim.battery <= LOW_BATTERY_PCT) {
          sim.lowBatteryFired = true;
          dispatch({
            type: "ALERT_RECEIVED",
            payload: {
              id: crypto.randomUUID(),
              alert_type: "LOW_BATTERY",
              severity: "WARNING",
              agent_id: sim.id,
              message: `${sim.displayName}: battery at ${sim.battery.toFixed(1)}%`,
              detected_at: now,
            },
          });
        }
      }

      dispatch({ type: "FLEET_UPDATE", payload: agents });
    };

    const intervalId = setInterval(tick, TICK_MS);
    // Run first tick immediately so the map isn't empty on mount
    tick();

    return () => clearInterval(intervalId);
  }, []);

  const loadTrail = async (agentId: string): Promise<void> => {
    const frames = historyRef.current.get(agentId) ?? [];
    // Return a snapshot of history so the player works even as new frames arrive
    dispatch({
      type: "REPLAY_LOADED",
      payload: { agentId, frames: [...frames] },
    });
  };

  const sendCommand = (agentId: string, commandType: CommandType): string => {
    const tempId = crypto.randomUUID();
    dispatch({
      type: "COMMAND_PENDING",
      payload: { tempId, agent_id: agentId, command_type: commandType },
    });

    // Simulate backend round-trip and apply the effect
    setTimeout(() => {
      const sim = simsRef.current.find((s) => s.id === agentId);
      if (!sim) {
        dispatch({
          type: "COMMAND_ERROR_RECEIVED",
          payload: { agent_id: agentId, error: "agent not found" },
        });
        dispatch({
          type: "TOAST_PUSH",
          payload: {
            id: crypto.randomUUID(),
            kind: "error",
            message: "Command failed: agent not found",
          },
        });
        return;
      }

      sim.mode =
        commandType === "LAND"
          ? "LANDING"
          : commandType === "RTH"
            ? "RTH"
            : "CUT";

      dispatch({
        type: "COMMAND_SENT_RECEIVED",
        payload: {
          agent_id: agentId,
          command_id: crypto.randomUUID(),
          issued_at: new Date().toISOString(),
        },
      });
      dispatch({
        type: "TOAST_PUSH",
        payload: {
          id: crypto.randomUUID(),
          kind: "success",
          message: `${commandType} dispatched`,
        },
      });
    }, 250);

    return tempId;
  };

  return (
    <FleetContext.Provider value={{ state, dispatch, loadTrail, sendCommand }}>
      {children}
    </FleetContext.Provider>
  );
}

// ── Sim physics ────────────────────────────────────────────────────────────────

function advanceSim(sim: AgentSim): void {
  // Battery always drains
  sim.battery = Math.max(0, sim.battery - sim.drainPerTick);

  switch (sim.mode) {
    case "ORBIT": {
      sim.angle += sim.angularStep;
      sim.lat = sim.centerLat + sim.radius * Math.sin(sim.angle);
      sim.lon = sim.centerLon + sim.radius * Math.cos(sim.angle);
      sim.altitude = 50 + Math.sin(sim.angle * 3) * 2;
      return;
    }
    case "LANDING": {
      sim.altitude = Math.max(0, sim.altitude - LAND_DESCENT_M_PER_TICK);
      if (sim.altitude === 0) sim.mode = "LANDED";
      return;
    }
    case "RTH": {
      const dlat = sim.centerLat - sim.lat;
      const dlon = sim.centerLon - sim.lon;
      const dist = Math.sqrt(dlat * dlat + dlon * dlon);
      if (dist <= RTH_STEP_DEG) {
        sim.lat = sim.centerLat;
        sim.lon = sim.centerLon;
        sim.mode = "LANDING";
      } else {
        const scale = RTH_STEP_DEG / dist;
        sim.lat += dlat * scale;
        sim.lon += dlon * scale;
      }
      return;
    }
    case "CUT": {
      sim.altitude = 0;
      sim.mode = "LANDED";
      return;
    }
    case "LANDED":
      return;
  }
}
