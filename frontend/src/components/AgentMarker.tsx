import L from "leaflet";
import { useMemo } from "react";
import { Marker } from "react-leaflet";
import { useFleet } from "../context/FleetContext";
import type { AgentState, ReplayState } from "../types/fleet";
import { buildMarkerHtml } from "../utils/agentStyle";

function livePosition(agent: AgentState): [number, number] {
  return [agent.latitude, agent.longitude];
}

function replayPosition(
  agent: AgentState,
  replay: ReplayState,
): [number, number] {
  if (
    replay.agentId === agent.agent_id &&
    replay.frames.length > 0
  ) {
    const f = replay.frames[replay.currentIndex];
    return [f.latitude, f.longitude];
  }
  return livePosition(agent);
}

interface Props {
  agent: AgentState;
}

export function AgentMarker({ agent }: Props) {
  const { state, dispatch } = useFleet();
  const isSelected = state.selectedAgentId === agent.agent_id;

  const position = replayPosition(agent, state.replay);

  const icon = useMemo(
    () =>
      L.divIcon({
        html: buildMarkerHtml(agent, isSelected),
        className: "agent-marker-host",
        iconSize: [38, 38],
        iconAnchor: [19, 19],
        popupAnchor: [0, -22],
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      agent.battery_pct,
      agent.status,
      agent.link_status,
      agent.device_type,
      isSelected,
    ],
  );

  return (
    <Marker
      position={position}
      icon={icon}
      eventHandlers={{
        click: () =>
          dispatch({ type: "SELECT_AGENT", payload: agent.agent_id }),
      }}
    />
  );
}
