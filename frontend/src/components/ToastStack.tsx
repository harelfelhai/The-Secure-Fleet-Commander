import { useEffect } from "react";
import { useFleet } from "../context/FleetContext";

const AUTO_DISMISS_MS = 4_000;

export function ToastStack() {
  const { state, dispatch } = useFleet();
  const { toasts } = state;

  useEffect(() => {
    if (toasts.length === 0) return;
    const oldest = toasts[0];
    const id = setTimeout(
      () => dispatch({ type: "TOAST_DISMISS", payload: oldest.id }),
      AUTO_DISMISS_MS,
    );
    return () => clearTimeout(id);
  }, [toasts, dispatch]);

  if (toasts.length === 0) return null;

  return (
    <div className="absolute bottom-4 right-4 z-30 flex flex-col gap-2">
      {toasts.map((t) => {
        const styles =
          t.kind === "success"
            ? "border-green-700 bg-green-950 text-green-200"
            : t.kind === "error"
              ? "border-red-700 bg-red-950 text-red-200"
              : "border-blue-700 bg-blue-950 text-blue-200";
        const icon = t.kind === "success" ? "✓" : t.kind === "error" ? "✕" : "ℹ";
        return (
          <div
            key={t.id}
            className={`flex w-72 items-start gap-3 rounded-lg border p-3 shadow-xl ${styles}`}
          >
            <span className="mt-0.5 text-lg" aria-hidden>
              {icon}
            </span>
            <p className="flex-1 text-sm leading-snug">{t.message}</p>
            <button
              onClick={() =>
                dispatch({ type: "TOAST_DISMISS", payload: t.id })
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
