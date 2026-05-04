import { useEffect } from "react";
import { useFleet } from "../context/FleetContext";
import type { SpeedMultiplier } from "../types/fleet";

const SPEEDS: SpeedMultiplier[] = [1, 2, 5, 10];
// Base interval: advance one frame every 400 ms at 1×.
// At 2× → 200 ms, at 5× → 80 ms, at 10× → 40 ms.
const BASE_INTERVAL_MS = 400;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ReplayControls() {
  const { state, dispatch } = useFleet();
  const { replay } = state;

  // Timer — advances the replay when playing.  Runs as a side effect so the
  // reducer stays pure.
  useEffect(() => {
    if (!replay.isPlaying || replay.frames.length === 0) return;
    const ms = Math.floor(BASE_INTERVAL_MS / replay.speedMultiplier);
    const id = setInterval(() => dispatch({ type: "REPLAY_ADVANCE" }), ms);
    return () => clearInterval(id);
  }, [replay.isPlaying, replay.speedMultiplier, replay.frames.length, dispatch]);

  if (!replay.agentId || replay.frames.length === 0) return null;

  const current = replay.frames[replay.currentIndex];
  const agentName =
    state.agents[replay.agentId]?.display_name ?? replay.agentId;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-20 border-t border-gray-700 bg-gray-900/95 px-4 py-3 backdrop-blur-sm">
      {/* Top row: agent name + frame info */}
      <div className="mb-2 flex items-center justify-between text-xs text-gray-400">
        <span className="font-medium text-white">{agentName} — Replay</span>
        {current && (
          <span className="font-mono">
            {formatTime(current.recorded_at)} &nbsp;|&nbsp;
            🔋 {current.battery_pct.toFixed(1)}% &nbsp;|&nbsp;
            ↑ {current.altitude_m.toFixed(1)} m
          </span>
        )}
        <span>
          {replay.currentIndex + 1} / {replay.frames.length}
        </span>
      </div>

      {/* Slider */}
      <input
        type="range"
        className="replay-slider mb-3 block"
        min={0}
        max={replay.frames.length - 1}
        value={replay.currentIndex}
        onChange={(e) =>
          dispatch({ type: "REPLAY_SEEK", payload: parseInt(e.target.value) })
        }
      />

      {/* Controls row */}
      <div className="flex items-center gap-2">
        {/* Rewind to start */}
        <button
          onClick={() => dispatch({ type: "REPLAY_SEEK", payload: 0 })}
          className="rounded px-2 py-1 text-sm text-gray-300 hover:bg-gray-700"
          title="Jump to start"
        >
          ⏮
        </button>

        {/* Play / Pause */}
        {replay.isPlaying ? (
          <button
            onClick={() => dispatch({ type: "REPLAY_PAUSE" })}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-500"
          >
            ⏸ Pause
          </button>
        ) : (
          <button
            onClick={() => dispatch({ type: "REPLAY_PLAY" })}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-500"
          >
            ▶ Play
          </button>
        )}

        {/* Speed selector */}
        <div className="ml-2 flex gap-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() =>
                dispatch({ type: "REPLAY_SET_SPEED", payload: s })
              }
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                replay.speedMultiplier === s
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:bg-gray-700 hover:text-white"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>

        {/* Close replay */}
        <button
          onClick={() => dispatch({ type: "REPLAY_CLOSE" })}
          className="ml-auto rounded px-2 py-1 text-sm text-gray-400 hover:bg-gray-700 hover:text-white"
          title="Exit replay"
        >
          ✕ Exit
        </button>
      </div>
    </div>
  );
}
