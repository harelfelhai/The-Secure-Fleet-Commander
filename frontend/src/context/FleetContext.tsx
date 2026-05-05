import {
  createContext,
  useContext,
  type Dispatch,
  type ReactNode,
} from "react";
import type { AppState, CommandType } from "../types/fleet";
import type { FleetAction } from "./fleet.reducer";

// ── Context value shape ────────────────────────────────────────────────────────

export interface FleetContextValue {
  state: AppState;
  dispatch: Dispatch<FleetAction>;
  /** Load trail frames for an agent, then dispatch REPLAY_LOADED. */
  loadTrail: (agentId: string) => Promise<void>;
  /** Issue an emergency command. Returns the client tempId. */
  sendCommand: (agentId: string, commandType: CommandType) => string;
}

// ── Context object ─────────────────────────────────────────────────────────────

export const FleetContext = createContext<FleetContextValue | null>(null);

// ── Consumer hook ──────────────────────────────────────────────────────────────

export function useFleet(): FleetContextValue {
  const ctx = useContext(FleetContext);
  if (!ctx) throw new Error("useFleet must be used inside a fleet provider");
  return ctx;
}

// ── Provider children prop helper ──────────────────────────────────────────────

export interface FleetProviderProps {
  children: ReactNode;
}
