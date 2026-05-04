import { MockFleetProvider } from "./providers/MockFleetProvider";
import { RealFleetProvider } from "./providers/RealFleetProvider";
import { FleetMap } from "./components/FleetMap";
import { AgentSidebar } from "./components/AgentSidebar";
import { ReplayControls } from "./components/ReplayControls";
import { AlertToast } from "./components/AlertToast";
import { ConnectionOverlay } from "./components/ConnectionOverlay";
import { useFleet } from "./context/FleetContext";

// ── Status bar ─────────────────────────────────────────────────────────────────

function StatusBar() {
  const { state } = useFleet();
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

        {hasSidebar && <AgentSidebar />}
        {hasReplay && <ReplayControls />}
        <AlertToast />
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
