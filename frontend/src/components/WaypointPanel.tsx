import { useFleet } from "../context/FleetContext";

export function WaypointPanel() {
  const { state, dispatch } = useFleet();
  const { waypoints } = state;

  return (
    <div className="absolute right-4 top-4 z-[1000] flex w-64 flex-col gap-2 rounded-lg border border-blue-500 bg-gray-900/95 p-4 shadow-xl">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-blue-400">Mission Waypoints</h2>
        <span className="text-xs text-gray-500">{waypoints.length} point{waypoints.length !== 1 ? "s" : ""}</span>
      </div>

      <p className="text-xs text-gray-400">
        Click on the map to place waypoints. They are connected in order.
      </p>

      {waypoints.length === 0 ? (
        <p className="py-2 text-center text-xs text-gray-600 italic">No waypoints yet</p>
      ) : (
        <ol className="max-h-56 overflow-y-auto">
          {waypoints.map((wp, idx) => (
            <li
              key={wp.id}
              className="flex items-center justify-between border-b border-gray-700 py-1.5 last:border-0"
            >
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-yellow-500 text-xs font-bold text-gray-900">
                  {idx + 1}
                </span>
                <span className="text-xs text-gray-300">
                  {wp.lat.toFixed(5)}, {wp.lng.toFixed(5)}
                </span>
              </div>
              <button
                onClick={() => dispatch({ type: "WAYPOINT_REMOVE", payload: wp.id })}
                className="ml-2 text-gray-500 hover:text-red-400 transition-colors"
                title="Remove waypoint"
                aria-label={`Remove waypoint ${idx + 1}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ol>
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => dispatch({ type: "WAYPOINTS_CLEAR" })}
          disabled={waypoints.length === 0}
          className="flex-1 rounded bg-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
        >
          Clear All
        </button>
        <button
          onClick={() => dispatch({ type: "PLAN_MODE_TOGGLE" })}
          className="flex-1 rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 transition-colors"
        >
          Exit Planning
        </button>
      </div>
    </div>
  );
}
