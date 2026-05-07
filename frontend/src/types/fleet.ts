export type DeviceType = "DRONE" | "ROVER";
export type AgentOnlineStatus = "ONLINE" | "STALE";
export type LinkStatus = "LINKED" | "RADIO_LOST" | "CLOUD_LOST";
export type WsStatus = "CONNECTING" | "OPEN" | "CLOSED";
export type SpeedMultiplier = 1 | 2 | 5 | 10;
export type AgentColor = "green" | "yellow" | "red" | "grey";
export type CommandType = "LAND" | "RTH" | "CUT_MOTORS";
export type CommandStatus = "PENDING" | "SENT" | "FAILED";

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

export interface ZonePolygon {
  name: string;
  latlngs: [number, number][]; // [lat, lon] pairs ready for Leaflet
}

export interface ReceivedAlert {
  id: string; // client-generated for React key + dismiss
  alert_type: "GEOFENCE_VIOLATION" | "LOW_BATTERY";
  severity: "WARNING" | "CRITICAL";
  agent_id: string;
  message: string;
  detected_at: string;
}

export interface CommandRecord {
  id: string; // tempId while PENDING, server command_id once SENT
  agent_id: string;
  command_type: CommandType;
  status: CommandStatus;
  issued_at: string; // ISO-8601
  error?: string;
}

export interface Toast {
  id: string;
  kind: "success" | "error" | "info";
  message: string;
}

export interface ReplayState {
  agentId: string | null;
  frames: TrailPoint[];
  currentIndex: number;
  isPlaying: boolean;
  speedMultiplier: SpeedMultiplier;
}

export interface PlanWaypoint {
  id: string;
  lat: number;
  lng: number;
}

export interface AppState {
  agents: Record<string, AgentState>;
  zones: ZonePolygon[];
  selectedAgentId: string | null;
  replay: ReplayState;
  alerts: ReceivedAlert[];
  commands: CommandRecord[];
  toasts: Toast[];
  wsStatus: WsStatus;
  batteryHistory: Record<string, number[]>; // agent_id → last 60 readings
  planMode: boolean;
  waypoints: PlanWaypoint[];
}
