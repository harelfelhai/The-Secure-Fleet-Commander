import { useCallback, useEffect, useRef } from "react";
import type { Dispatch } from "react";
import type { AgentState } from "../types/fleet";
import type { FleetAction } from "../context/fleet.reducer";

const WS_URL = "/ws/fleet/live";
const MAX_BACKOFF_MS = 30_000;

interface FleetUpdateMessage {
  msg_type: "FLEET_UPDATE";
  agents: AgentState[];
}

interface AlertMessage {
  msg_type: "ALERT";
  alert_type: "GEOFENCE_VIOLATION" | "LOW_BATTERY";
  severity: "WARNING" | "CRITICAL";
  agent_id: string;
  message: string;
  detected_at: string;
}

type InboundMessage = FleetUpdateMessage | AlertMessage | { msg_type: string };

export function useFleetSocket(dispatch: Dispatch<FleetAction>): void {
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1_000);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFirstConnect = useRef(true);

  const syncFleet = useCallback(() => {
    fetch("/api/agents/snapshot")
      .then((r) => r.json())
      .then((agents: AgentState[]) =>
        dispatch({ type: "SYNC_COMPLETE", payload: agents }),
      )
      .catch((err: unknown) =>
        console.warn("Fleet snapshot sync failed:", err),
      );
  }, [dispatch]);

  const connect = useCallback(() => {
    dispatch({ type: "WS_STATUS", payload: "CONNECTING" });

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      backoffRef.current = 1_000; // reset backoff on success
      dispatch({ type: "WS_STATUS", payload: "OPEN" });
      if (!isFirstConnect.current) {
        // Reconnect after a drop — fetch current snapshot instead of waiting
        // for the next FLEET_UPDATE, so the map is correct immediately.
        syncFleet();
      }
      isFirstConnect.current = false;
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      let msg: InboundMessage;
      try {
        msg = JSON.parse(event.data) as InboundMessage;
      } catch {
        console.warn("Invalid JSON from WS:", event.data);
        return;
      }

      if (msg.msg_type === "FLEET_UPDATE") {
        dispatch({
          type: "FLEET_UPDATE",
          payload: (msg as FleetUpdateMessage).agents,
        });
      } else if (msg.msg_type === "ALERT") {
        const alert = msg as AlertMessage;
        dispatch({
          type: "ALERT_RECEIVED",
          payload: {
            id: crypto.randomUUID(),
            alert_type: alert.alert_type,
            severity: alert.severity,
            agent_id: alert.agent_id,
            message: alert.message,
            detected_at: alert.detected_at,
          },
        });
      }
    };

    ws.onclose = () => {
      dispatch({ type: "WS_STATUS", payload: "CLOSED" });
      timerRef.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        connect();
      }, backoffRef.current);
    };

    ws.onerror = () => ws.close();
  }, [dispatch, syncFleet]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [connect]);
}
