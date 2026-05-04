import { useFleet } from "../context/FleetContext";

export function ConnectionOverlay() {
  const { state } = useFleet();

  if (state.wsStatus !== "CLOSED") return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="rounded-xl bg-gray-900 p-8 text-center shadow-2xl">
        <div className="mb-4 text-4xl">📡</div>
        <h2 className="mb-2 text-xl font-bold text-white">Connection Lost</h2>
        <p className="text-sm text-gray-400">
          Reconnecting to Fleet Commander…
        </p>
        <div className="mt-4 flex justify-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-2 w-2 animate-bounce rounded-full bg-blue-400"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
