import type {
  AgentState,
  AppState,
  ReceivedAlert,
  SpeedMultiplier,
  TrailPoint,
  WsStatus,
} from "../types/fleet";

// ── Actions ────────────────────────────────────────────────────────────────────

export type FleetAction =
  // WebSocket data
  | { type: "FLEET_UPDATE"; payload: AgentState[] }
  | { type: "SYNC_COMPLETE"; payload: AgentState[] } // REST snapshot on reconnect
  | { type: "ALERT_RECEIVED"; payload: ReceivedAlert }
  | { type: "ALERT_DISMISS"; payload: string } // alert id
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
  // Connection
  | { type: "WS_STATUS"; payload: WsStatus };

// ── Initial state ─────────────────────────────────────────────────────────────

export const initialState: AppState = {
  agents: {},
  selectedAgentId: null,
  replay: {
    agentId: null,
    frames: [],
    currentIndex: 0,
    isPlaying: false,
    speedMultiplier: 1,
  },
  alerts: [],
  wsStatus: "CONNECTING",
};

// ── Reducer ───────────────────────────────────────────────────────────────────

export function fleetReducer(state: AppState, action: FleetAction): AppState {
  switch (action.type) {
    case "FLEET_UPDATE":
    case "SYNC_COMPLETE": {
      const agents: Record<string, AgentState> = {};
      for (const a of action.payload) {
        agents[a.agent_id] = a;
      }
      return { ...state, agents };
    }

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

    case "WS_STATUS":
      return { ...state, wsStatus: action.payload };

    default:
      return state;
  }
}
