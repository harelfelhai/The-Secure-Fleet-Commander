export type DeviceType = "DRONE" | "ROVER";
export type AgentOnlineStatus = "ONLINE" | "STALE";
export type LinkStatus = "LINKED" | "RADIO_LOST" | "CLOUD_LOST";
export type WsStatus = "CONNECTING" | "OPEN" | "CLOSED";
export type SpeedMultiplier = 1 | 2 | 5 | 10;
export type AgentColor = "green" | "yellow" | "red" | "grey";

export interface AgentState {
  agent_id: string;
  display_name: string;
  device_type: DeviceType;
  latitude: number;
  longitude: number;
  altitude_m: number;
  battery_pct: number;
  last_seen_at: string; // ISO-8601
  mission_start_at: string | null; // ISO-8601 or null
  status: AgentOnlineStatus;
  link_status: LinkStatus;
}

export interface TrailPoint {
  latitude: number;
  longitude: number;
  altitude_m: number;
  battery_pct: number;
  recorded_at: string; // ISO-8601
}

export interface ReceivedAlert {
  id: string; // client-generated for React key + dismiss
  alert_type: "GEOFENCE_VIOLATION" | "LOW_BATTERY";
  severity: "WARNING" | "CRITICAL";
  agent_id: string;
  message: string;
  detected_at: string;
}

export interface ReplayState {
  agentId: string | null;
  frames: TrailPoint[];
  currentIndex: number;
  isPlaying: boolean;
  speedMultiplier: SpeedMultiplier;
}

export interface AppState {
  agents: Record<string, AgentState>;
  selectedAgentId: string | null;
  replay: ReplayState;
  alerts: ReceivedAlert[];
  wsStatus: WsStatus;
}
