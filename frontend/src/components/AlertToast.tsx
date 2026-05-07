import { useEffect, useRef } from "react";
import { useFleet } from "../context/FleetContext";

const AUTO_DISMISS_MS = 6_000;

function playAlertBeep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
    // Close the context after the beep to release the audio resource
    setTimeout(() => void ctx.close(), 500);
  } catch {
    // AudioContext may be blocked before user interaction — fail silently
  }
}

export function AlertToast() {
  const { state, dispatch } = useFleet();
  const { alerts } = state;
  const lastPlayedId = useRef<string | null>(null);

  // Auto-dismiss each alert after AUTO_DISMISS_MS
  useEffect(() => {
    if (alerts.length === 0) return;
    const oldest = alerts[alerts.length - 1];
    const id = setTimeout(
      () => dispatch({ type: "ALERT_DISMISS", payload: oldest.id }),
      AUTO_DISMISS_MS,
    );
    return () => clearTimeout(id);
  }, [alerts, dispatch]);

  // Play a beep for each new CRITICAL alert
  useEffect(() => {
    if (alerts.length === 0) return;
    const newest = alerts[0];
    if (newest.severity === "CRITICAL" && newest.id !== lastPlayedId.current) {
      lastPlayedId.current = newest.id;
      playAlertBeep();
    }
  }, [alerts]);

  if (alerts.length === 0) return null;

  return (
    <div className="absolute right-4 top-4 z-30 flex flex-col gap-2">
      {alerts.slice(0, 5).map((alert) => {
        const isCritical = alert.severity === "CRITICAL";
        return (
          <div
            key={alert.id}
            className={`flex w-72 items-start gap-3 rounded-lg p-3 shadow-xl ${
              isCritical
                ? "border border-red-700 bg-red-950 text-red-200"
                : "border border-yellow-700 bg-yellow-950 text-yellow-200"
            }`}
          >
            <span className="mt-0.5 text-lg" aria-hidden>
              {isCritical ? "🔴" : "🟡"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wide opacity-75">
                {alert.alert_type.replace("_", " ")}
              </p>
              <p className="mt-0.5 text-sm leading-snug">{alert.message}</p>
            </div>
            <button
              onClick={() =>
                dispatch({ type: "ALERT_DISMISS", payload: alert.id })
              }
              className="shrink-0 text-xs opacity-50 hover:opacity-100"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
