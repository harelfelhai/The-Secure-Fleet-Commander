import { useState } from "react";
import { useFleet } from "../context/FleetContext";
import type { AgentState, CommandType } from "../types/fleet";
import { CommandConfirmModal } from "./CommandConfirmModal";

interface Props {
  agent: AgentState;
}

const BUTTONS: Array<{
  type: CommandType;
  label: string;
  className: string;
}> = [
  {
    type: "LAND",
    label: "Land",
    className: "bg-yellow-600 hover:bg-yellow-500",
  },
  {
    type: "RTH",
    label: "Return Home",
    className: "bg-blue-600 hover:bg-blue-500",
  },
  {
    type: "CUT_MOTORS",
    label: "Cut Motors",
    className: "bg-red-700 hover:bg-red-600",
  },
];

export function EmergencyCommands({ agent }: Props) {
  const { state, sendCommand } = useFleet();
  const [pendingType, setPendingType] = useState<CommandType | null>(null);

  const offline =
    agent.status !== "ONLINE" || agent.link_status !== "LINKED";

  const hasPending = state.commands.some(
    (c) => c.agent_id === agent.agent_id && c.status === "PENDING",
  );

  const disabled = offline || hasPending;

  const onConfirm = () => {
    if (pendingType) sendCommand(agent.agent_id, pendingType);
    setPendingType(null);
  };

  return (
    <>
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Emergency Commands
        </p>
        {offline && (
          <p className="text-xs text-gray-400">
            Agent is offline — commands disabled.
          </p>
        )}
        <div className="grid gap-2">
          {BUTTONS.map((b) => (
            <button
              key={b.type}
              type="button"
              disabled={disabled}
              onClick={() => setPendingType(b.type)}
              className={`rounded-lg py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-50 ${b.className}`}
            >
              {hasPending ? "Sending…" : b.label}
            </button>
          ))}
        </div>
      </div>

      {pendingType && (
        <CommandConfirmModal
          agentDisplayName={agent.display_name}
          commandType={pendingType}
          onConfirm={onConfirm}
          onCancel={() => setPendingType(null)}
        />
      )}
    </>
  );
}
