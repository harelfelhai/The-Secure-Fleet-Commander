import { MockFleetProvider } from "./providers/MockFleetProvider";
import { RealFleetProvider } from "./providers/RealFleetProvider";
import { FleetMap } from "./components/FleetMap";
import { AgentSidebar } from "./components/AgentSidebar";
import { ReplayControls } from "./components/ReplayControls";
import { AlertToast } from "./components/AlertToast";
import { ConnectionOverlay } from "./components/ConnectionOverlay";
import { ToastStack } from "./components/ToastStack";
import { WaypointPanel } from "./components/WaypointPanel";
import { useFleet } from "./context/FleetContext";

// ── Status bar ─────────────────────────────────────────────────────────────────

function StatusBar() {
  const { state, dispatch } = useFleet();
  const agentCount = Object.keys(state.agents).length;
  const wsColour =
    state.wsStatus === "OPEN"
      ? "text-green-400"
      : state.wsStatus === "CONNECTING"
        ? "text-yellow-400"
        : "text-red-400";
  const wsLabel =
    state.wsStatus === "OPEN"
      ? "Connected"
      : state.wsStatus === "CONNECTING"
        ? "Connecting…"
        : "Disconnected";

  return (
    <header className="flex h-10 shrink-0 items-center justify-between border-b border-gray-700 bg-gray-900 px-4">
      <span className="text-sm font-bold tracking-wide text-white">
        ⬡ Fleet Commander
      </span>
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span>
          {agentCount} agent{agentCount !== 1 ? "s" : ""}
        </span>
        <button
          onClick={() => dispatch({ type: "PLAN_MODE_TOGGLE" })}
          className={`rounded px-2 py-0.5 font-semibold transition-colors ${
            state.planMode
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-gray-700 text-gray-300 hover:bg-gray-600"
          }`}
          title={state.planMode ? "Exit Plan Mode" : "Enter Plan Mode"}
        >
          {state.planMode ? "✎ Planning" : "✎ Plan"}
        </button>
        <span className={wsColour}>● {wsLabel}</span>
      </div>
    </header>
  );
}

// ── Main layout ────────────────────────────────────────────────────────────────

function Layout() {
  const { state } = useFleet();
  const hasSidebar = state.selectedAgentId !== null;
  const hasReplay =
    state.replay.agentId !== null && state.replay.frames.length > 0;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-950 text-white">
      <StatusBar />

      <div className="relative flex-1 overflow-hidden">
        {/* Dim map when disconnected */}
        <div
          className={`h-full w-full transition-opacity duration-500 ${
            state.wsStatus === "CLOSED" ? "opacity-40" : "opacity-100"
          }`}
        >
          <FleetMap />
        </div>

        {hasSidebar && !state.planMode && <AgentSidebar />}
        {hasReplay && !state.planMode && <ReplayControls />}
        {state.planMode && <WaypointPanel />}
        <AlertToast />
        <ToastStack />
        <ConnectionOverlay />
      </div>
    </div>
  );
}

// ── Root ───────────────────────────────────────────────────────────────────────

const useMock =
  import.meta.env.VITE_USE_MOCK === "true" ||
  new URLSearchParams(window.location.search).get("mock") === "true";

export default function App() {
  const Provider = useMock ? MockFleetProvider : RealFleetProvider;
  return (
    <Provider>
      <Layout />
    </Provider>
  );
}
