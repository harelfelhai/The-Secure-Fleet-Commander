import type {
  AgentState,
  AppState,
  CommandRecord,
  CommandType,
  PlanWaypoint,
  ReceivedAlert,
  SpeedMultiplier,
  Toast,
  TrailPoint,
  WsStatus,
  ZonePolygon,
} from "../types/fleet";

// ── Actions ────────────────────────────────────────────────────────────────────

export type FleetAction =
  // WebSocket data
  | { type: "FLEET_UPDATE"; payload: AgentState[] }
  | { type: "SYNC_COMPLETE"; payload: AgentState[] } // REST snapshot on reconnect
  | { type: "ALERT_RECEIVED"; payload: ReceivedAlert }
  | { type: "ALERT_DISMISS"; payload: string } // alert id
  // Zones
  | { type: "ZONES_LOADED"; payload: ZonePolygon[] }
  // Agent selection
  | { type: "SELECT_AGENT"; payload: string } // agent_id
  | { type: "DESELECT_AGENT" }
  // Replay / film mode
  | { type: "REPLAY_LOADED"; payload: { agentId: string; frames: TrailPoint[] } }
  | { type: "REPLAY_ADVANCE" } // advance one frame (called by timer effect)
  | { type: "REPLAY_SEEK"; payload: number } // seek to specific frame index
  | { type: "REPLAY_PLAY" }
  | { type: "REPLAY_PAUSE" }
  | { type: "REPLAY_SET_SPEED"; payload: SpeedMultiplier }
  | { type: "REPLAY_CLOSE" }
  // Commands
  | {
      type: "COMMAND_PENDING";
      payload: { tempId: string; agent_id: string; command_type: CommandType };
    }
  | {
      type: "COMMAND_SENT_RECEIVED";
      payload: { agent_id: string; command_id: string; issued_at: string };
    }
  | { type: "COMMAND_ERROR_RECEIVED"; payload: { agent_id: string; error: string } }
  // Toasts (transient operator feedback)
  | { type: "TOAST_PUSH"; payload: Toast }
  | { type: "TOAST_DISMISS"; payload: string } // toast id
  // Connection
  | { type: "WS_STATUS"; payload: WsStatus }
  // Plan mode
  | { type: "PLAN_MODE_TOGGLE" }
  | { type: "WAYPOINT_ADD"; payload: PlanWaypoint }
  | { type: "WAYPOINT_REMOVE"; payload: string } // waypoint id
  | { type: "WAYPOINTS_CLEAR" };

// ── Initial state ─────────────────────────────────────────────────────────────

const BATTERY_HISTORY_MAX = 60;

export const initialState: AppState = {
  agents: {},
  zones: [],
  selectedAgentId: null,
  batteryHistory: {},
  replay: {
    agentId: null,
    frames: [],
    currentIndex: 0,
    isPlaying: false,
    speedMultiplier: 1,
  },
  alerts: [],
  commands: [],
  toasts: [],
  wsStatus: "CONNECTING",
  planMode: false,
  waypoints: [],
};

// UI disables action buttons while a PENDING exists, so in practice there's
// at most one PENDING per agent. We still pick the oldest defensively.
function updateOldestPending(
  commands: CommandRecord[],
  agent_id: string,
  patch: Partial<CommandRecord>,
): CommandRecord[] {
  const idx = commands.findIndex(
    (c) => c.agent_id === agent_id && c.status === "PENDING",
  );
  if (idx < 0) return commands;
  const next = commands.slice();
  next[idx] = { ...next[idx], ...patch };
  return next;
}

// ── Reducer ───────────────────────────────────────────────────────────────────

export function fleetReducer(state: AppState, action: FleetAction): AppState {
  switch (action.type) {
    case "FLEET_UPDATE":
    case "SYNC_COMPLETE": {
      const agents: Record<string, AgentState> = {};
      const batteryHistory = { ...state.batteryHistory };
      for (const a of action.payload) {
        agents[a.agent_id] = a;
        const prev = batteryHistory[a.agent_id] ?? [];
        batteryHistory[a.agent_id] = [...prev, a.battery_pct].slice(
          -BATTERY_HISTORY_MAX,
        );
      }
      return { ...state, agents, batteryHistory };
    }

    case "ZONES_LOADED":
      return { ...state, zones: action.payload };

    case "ALERT_RECEIVED":
      return {
        ...state,
        alerts: [action.payload, ...state.alerts].slice(0, 20), // cap at 20
      };

    case "ALERT_DISMISS":
      return {
        ...state,
        alerts: state.alerts.filter((a) => a.id !== action.payload),
      };

    case "SELECT_AGENT":
      return { ...state, selectedAgentId: action.payload };

    case "DESELECT_AGENT":
      return { ...state, selectedAgentId: null };

    case "REPLAY_LOADED":
      return {
        ...state,
        replay: {
          agentId: action.payload.agentId,
          frames: action.payload.frames,
          currentIndex: 0,
          isPlaying: false,
          speedMultiplier: state.replay.speedMultiplier,
        },
      };

    case "REPLAY_ADVANCE": {
      const next = state.replay.currentIndex + 1;
      if (next >= state.replay.frames.length) {
        // Reached the end — pause at last frame
        return {
          ...state,
          replay: {
            ...state.replay,
            currentIndex: Math.max(0, state.replay.frames.length - 1),
            isPlaying: false,
          },
        };
      }
      return {
        ...state,
        replay: { ...state.replay, currentIndex: next },
      };
    }

    case "REPLAY_SEEK":
      return {
        ...state,
        replay: {
          ...state.replay,
          currentIndex: Math.max(
            0,
            Math.min(action.payload, state.replay.frames.length - 1),
          ),
        },
      };

    case "REPLAY_PLAY":
      return { ...state, replay: { ...state.replay, isPlaying: true } };

    case "REPLAY_PAUSE":
      return { ...state, replay: { ...state.replay, isPlaying: false } };

    case "REPLAY_SET_SPEED":
      return {
        ...state,
        replay: { ...state.replay, speedMultiplier: action.payload },
      };

    case "REPLAY_CLOSE":
      return {
        ...state,
        replay: { ...initialState.replay },
      };

    case "COMMAND_PENDING": {
      const record: CommandRecord = {
        id: action.payload.tempId,
        agent_id: action.payload.agent_id,
        command_type: action.payload.command_type,
        status: "PENDING",
        issued_at: new Date().toISOString(),
      };
      return {
        ...state,
        commands: [record, ...state.commands].slice(0, 50),
      };
    }

    case "COMMAND_SENT_RECEIVED":
      return {
        ...state,
        commands: updateOldestPending(state.commands, action.payload.agent_id, {
          id: action.payload.command_id,
          status: "SENT",
          issued_at: action.payload.issued_at,
        }),
      };

    case "COMMAND_ERROR_RECEIVED":
      return {
        ...state,
        commands: updateOldestPending(state.commands, action.payload.agent_id, {
          status: "FAILED",
          error: action.payload.error,
        }),
      };

    case "TOAST_PUSH":
      return {
        ...state,
        toasts: [...state.toasts, action.payload].slice(-5),
      };

    case "TOAST_DISMISS":
      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== action.payload),
      };

    case "WS_STATUS":
      return { ...state, wsStatus: action.payload };

    case "PLAN_MODE_TOGGLE":
      return { ...state, planMode: !state.planMode };

    case "WAYPOINT_ADD":
      return { ...state, waypoints: [...state.waypoints, action.payload] };

    case "WAYPOINT_REMOVE":
      return {
        ...state,
        waypoints: state.waypoints.filter((w) => w.id !== action.payload),
      };

    case "WAYPOINTS_CLEAR":
      return { ...state, waypoints: [] };

    default:
      return state;
  }
}
