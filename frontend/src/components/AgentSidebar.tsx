import { useFleet } from "../context/FleetContext";
import type { AgentState } from "../types/fleet";
import { getAgentColor } from "../utils/agentStyle";
import { EmergencyCommands } from "./EmergencyCommands";

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "N/A";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function BatteryBar({ agent }: { agent: AgentState }) {
  const color = getAgentColor(agent);
  const pct = Math.max(0, Math.min(100, agent.battery_pct));
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-gray-400">
        <span>Battery</span>
        <span className="font-semibold text-white">{pct.toFixed(1)}%</span>
      </div>
      <div className="battery-bar">
        <div
          className={`battery-bar__fill battery-bar__fill--${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StatusPill({
  label,
  value,
  variant,
}: {
  label: string;
  value: string;
  variant: "green" | "yellow" | "red" | "grey" | "blue";
}) {
  const colours = {
    green: "bg-green-900/50 text-green-300",
    yellow: "bg-yellow-900/50 text-yellow-300",
    red: "bg-red-900/50 text-red-300",
    grey: "bg-gray-700 text-gray-300",
    blue: "bg-blue-900/50 text-blue-300",
  };
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-400">{label}</span>
      <span className={`rounded px-2 py-0.5 text-xs font-medium ${colours[variant]}`}>
        {value}
      </span>
    </div>
  );
}

export function AgentSidebar() {
  const { state, dispatch, loadTrail } = useFleet();

  const agent = state.selectedAgentId
    ? state.agents[state.selectedAgentId]
    : null;

  if (!agent) return null;

  const linkVariant =
    agent.link_status === "LINKED"
      ? "green"
      : agent.link_status === "RADIO_LOST"
        ? "red"
        : "grey";
  const statusVariant = agent.status === "ONLINE" ? "green" : "grey";

  const isReplayingThis = state.replay.agentId === agent.agent_id;

  return (
    <div className="absolute right-0 top-0 z-20 flex h-full w-72 flex-col bg-gray-900/95 shadow-2xl backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-700 px-4 py-3">
        <div>
          <h2 className="font-bold text-white">{agent.display_name}</h2>
          <p className="text-xs text-gray-400">{agent.device_type}</p>
        </div>
        <div className="flex items-center gap-1">
          {isReplayingThis ? (
            <button
              onClick={() => dispatch({ type: "REPLAY_CLOSE" })}
              className="rounded-lg p-1.5 text-xs text-gray-300 hover:bg-gray-700 hover:text-white"
              aria-label="Stop replay"
              title="Stop replay"
            >
              ◼
            </button>
          ) : (
            <button
              onClick={() => void loadTrail(agent.agent_id)}
              className="rounded-lg p-1.5 text-xs text-gray-300 hover:bg-gray-700 hover:text-white"
              aria-label="Replay mission"
              title="Replay mission"
            >
              ▶
            </button>
          )}
          <button
            onClick={() => dispatch({ type: "DESELECT_AGENT" })}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-700 hover:text-white"
            aria-label="Close sidebar"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {/* Status pills */}
        <div className="space-y-2">
          <StatusPill label="Status" value={agent.status} variant={statusVariant} />
          <StatusPill label="Link" value={agent.link_status} variant={linkVariant} />
        </div>

        {/* Battery */}
        <BatteryBar agent={agent} />

        {/* Position */}
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Position
          </p>
          <div className="space-y-1 rounded-lg bg-gray-800 px-3 py-2 text-xs text-gray-300">
            <div className="flex justify-between">
              <span>Lat</span>
              <span className="font-mono">{agent.latitude.toFixed(5)}</span>
            </div>
            <div className="flex justify-between">
              <span>Lon</span>
              <span className="font-mono">{agent.longitude.toFixed(5)}</span>
            </div>
            <div className="flex justify-between">
              <span>Alt</span>
              <span className="font-mono">{agent.altitude_m.toFixed(1)} m</span>
            </div>
          </div>
        </div>

        {/* Timing */}
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Timing
          </p>
          <div className="space-y-1 rounded-lg bg-gray-800 px-3 py-2 text-xs text-gray-300">
            <div className="flex justify-between">
              <span>Mission start</span>
              <span className="font-mono">
                {formatDateTime(agent.mission_start_at)}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Last seen</span>
              <span className="font-mono text-gray-400">
                {formatRelativeTime(agent.last_seen_at)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer — emergency commands */}
      <div className="border-t border-gray-700 px-4 py-3">
        <EmergencyCommands agent={agent} />
      </div>
    </div>
  );
}
