import { useEffect, useState } from "react";
import type { CommandType } from "../types/fleet";

interface CommandMeta {
  label: string;
  description: string;
  buttonClass: string;
  requiresDoubleConfirm: boolean;
}

const META: Record<CommandType, CommandMeta> = {
  LAND: {
    label: "Land",
    description: "The agent will descend to ground at the current location.",
    buttonClass: "bg-yellow-600 hover:bg-yellow-500",
    requiresDoubleConfirm: false,
  },
  RTH: {
    label: "Return Home",
    description: "The agent will steer back to its launch point and land.",
    buttonClass: "bg-blue-600 hover:bg-blue-500",
    requiresDoubleConfirm: false,
  },
  CUT_MOTORS: {
    label: "Cut Motors",
    description:
      "Motors will be killed immediately. The agent will fall from current altitude. This action is irreversible.",
    buttonClass: "bg-red-600 hover:bg-red-500",
    requiresDoubleConfirm: true,
  },
};

interface Props {
  agentDisplayName: string;
  commandType: CommandType;
  onConfirm: () => void;
  onCancel: () => void;
}

export function CommandConfirmModal({
  agentDisplayName,
  commandType,
  onConfirm,
  onCancel,
}: Props) {
  const meta = META[commandType];
  const [armed, setArmed] = useState(!meta.requiresDoubleConfirm);

  // Esc closes the modal
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-white">
          {meta.label} — {agentDisplayName}
        </h2>
        <p className="mt-2 text-sm text-gray-300">{meta.description}</p>

        {meta.requiresDoubleConfirm && (
          <div className="mt-4 rounded-lg border border-red-800 bg-red-950/60 p-3 text-xs text-red-200">
            ⚠ Destructive action. Confirm twice to proceed.
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-600"
          >
            Cancel
          </button>

          {meta.requiresDoubleConfirm && !armed ? (
            <button
              type="button"
              onClick={() => setArmed(true)}
              className={`rounded-lg px-4 py-2 text-sm font-bold text-white ${meta.buttonClass}`}
            >
              Confirm
            </button>
          ) : (
            <button
              type="button"
              onClick={onConfirm}
              autoFocus
              className={`rounded-lg px-4 py-2 text-sm font-bold text-white ${meta.buttonClass}`}
            >
              {meta.requiresDoubleConfirm ? "Really Confirm" : "Confirm"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
