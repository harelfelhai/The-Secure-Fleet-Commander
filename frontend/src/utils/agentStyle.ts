import type { AgentColor, AgentState, DeviceType } from "../types/fleet";

// ── Colour derivation ─────────────────────────────────────────────────────────

/**
 * Returns a colour token for the agent marker, derived purely from the agent's
 * current state.  Thresholds mirror the backend rules engine:
 *   warn_pct = 20  →  alert fires
 *   clear_pct = 25 →  alert clears (hysteresis band)
 */
export function getAgentColor(agent: AgentState): AgentColor {
  if (agent.status === "STALE" || agent.link_status !== "LINKED") return "grey";
  if (agent.battery_pct > 25) return "green";
  if (agent.battery_pct > 15) return "yellow";
  return "red";
}

// ── SVG icons (inline strings for DivIcon) ────────────────────────────────────

const DRONE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="currentColor" stroke-width="1.8"
     stroke-linecap="round" stroke-linejoin="round"
     width="20" height="20">
  <!-- body -->
  <rect x="10" y="10" width="4" height="4" rx="1" fill="currentColor" stroke="none"/>
  <!-- arms -->
  <line x1="12" y1="12" x2="5"  y2="5"/>
  <line x1="12" y1="12" x2="19" y2="5"/>
  <line x1="12" y1="12" x2="5"  y2="19"/>
  <line x1="12" y1="12" x2="19" y2="19"/>
  <!-- rotors -->
  <circle cx="5"  cy="5"  r="2.5"/>
  <circle cx="19" cy="5"  r="2.5"/>
  <circle cx="5"  cy="19" r="2.5"/>
  <circle cx="19" cy="19" r="2.5"/>
</svg>`;

const ROVER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="currentColor" width="20" height="20">
  <!-- body -->
  <rect x="5" y="8" width="14" height="8" rx="2"/>
  <!-- wheels -->
  <rect x="2"  y="7"  width="3" height="5" rx="1"/>
  <rect x="19" y="7"  width="3" height="5" rx="1"/>
  <rect x="2"  y="12" width="3" height="5" rx="1"/>
  <rect x="19" y="12" width="3" height="5" rx="1"/>
</svg>`;

export function getDeviceSvg(deviceType: DeviceType): string {
  return deviceType === "DRONE" ? DRONE_SVG : ROVER_SVG;
}

// ── DivIcon HTML factory ──────────────────────────────────────────────────────

export function buildMarkerHtml(
  agent: AgentState,
  isSelected: boolean,
): string {
  const color = getAgentColor(agent);
  const svg = getDeviceSvg(agent.device_type);
  const isOffline =
    agent.status === "STALE" || agent.link_status !== "LINKED";
  const selectedClass = isSelected ? " agent-marker--selected" : "";

  return `
    <div class="agent-marker agent-marker--${color}${selectedClass}">
      ${svg}
      ${isOffline ? '<div class="agent-marker__offline-badge">!</div>' : ""}
    </div>`;
}
