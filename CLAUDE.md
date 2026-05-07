# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Secure Fleet Commander** is a real-time Safety Monitor C2 (Command & Control) system for autonomous drone/rover fleets. It has three independent Python/JS packages in a monorepo:

- `backend/` — FastAPI + SQLAlchemy 2.x async REST + WebSocket server
- `gateway/` — Python asyncio process running on each physical gateway device
- `frontend/` — React 18 + TypeScript + Vite SPA (map UI)

## Commands

### Backend

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head        # apply DB migrations
uvicorn app.main:app --reload

# Tests (requires Postgres; see env vars below)
pytest -v --tb=short
pytest tests/test_ingestion.py -v   # single file
pytest -k "test_backfill" -v        # single test by name

# Lint / format
ruff check .
black --check .
black .    # auto-format
```

Required env vars for tests (set in shell or `.env`):
```
DATABASE_URL=postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_commander_test
JWT_SECRET=ci-test-secret
ZONES_CONFIG_PATH=../shared/schemas/zones.json
```

### Gateway

```bash
cd gateway
pip install -e ".[dev]"
python -m app.main

pytest -v
pytest tests/test_gateway_client.py -v
ruff check .
black --check .
```

### Frontend

```bash
cd frontend
npm ci                     # strict install — use this, not npm install
npm run dev                # Vite dev server at http://localhost:5173
npm run typecheck          # tsc --noEmit
npm run lint               # ESLint, max-warnings 0
npm run build              # production build

# Mock mode (no backend needed)
VITE_USE_MOCK=true npm run dev
# or open: http://localhost:5173?mock=true
```

### Infrastructure

```bash
cd infra
docker compose up -d       # PostgreSQL 16 on :5432, pgAdmin on :5050
```

## Architecture

### Data Flow

```
SimulatedDroneAdapter
        │ read_telemetry() → TelemetryFrame (5 Hz)
        ▼
   GatewayClient (gateway/)
     Task A: live producer  ──────────────────────────────────┐ asyncio.Lock
     Task B: buffer drainer (is_backfill=True on reconnect)  ─┤ (_send_lock)
     Task C: command receiver (recv COMMAND → adapter → ACK) ─┘
        │ WS /ws/gateway/{hardware_id}?token=<JWT>
        ▼
   Backend WS router (ws.py)
        │
        ├─► IngestionService.ingest()
        │       ├─ RulesEngine.evaluate()   → InternalAlert[]
        │       ├─ FleetBroadcaster.update_agent()
        │       ├─ broadcaster.broadcast_fleet_update()  → all frontend WS clients
        │       └─ _persist() → GpsBreadcrumb row (throttled to persist_interval_seconds=2s)
        │
        └─► Frontend WS /ws/fleet/live
                │ FLEET_UPDATE (every frame)
                │ ALERT (on rule trigger)
                ▼
           useFleetSocket (React hook)
                │ dispatch() → fleetReducer
                ▼
           FleetContext → FleetMap + AgentSidebar + ReplayControls
```

### Backend Service Layer

**`app/services/ingestion.py` — `IngestionService`**
The core ingest pipeline for each telemetry frame. Key design:
- Backfill frames (`is_backfill=True`) skip rules, alerts, broadcaster update, and `last_seen_at` DB update — they only persist breadcrumbs.
- Throttle uses **event time** (`frame.timestamp`), not server clock — `_event_elapsed(frame.timestamp, ctx.last_persisted_at)`. This is critical: during buffer drains, server-side elapsed is near-zero so all frames would collapse to one breadcrumb if we used `datetime.now()`.
- `IngestionContext` is a per-session dataclass that lives for the lifetime of one gateway WS connection. `last_persisted_at` is updated in place.

**`app/services/broadcaster.py` — `FleetBroadcaster`**
In-memory fleet state dict (`_fleet: dict[str, AgentStatus]`). Singleton via `lru_cache` in `dependencies.py`.
- `update_agent()` has a stale-frame guard: if `frame.last_seen_at <= current.last_seen_at`, the update is silently dropped. This prevents backfill from overwriting live state.
- `mark_cloud_lost(gateway_hardware_id)` marks all agents on that gateway as `status=STALE, link_status=CLOUD_LOST`.
- `mark_link_status(agent_id, ...)` handles radio-only drops (gateway still connected to cloud).

**`app/services/rules_engine.py` — `RulesEngine`**
Pure evaluation, no I/O. Per-agent `RuleContext` holds dedup state (`active_zones`, `low_battery_active`, `prior_battery_pct`). Rules are edge-triggered (fire once on entry, suppress while inside). `clear_agent_state()` must be called on gateway disconnect to reset hysteresis.

**Rules:**
- `GeofenceRule` — fires `GEOFENCE_VIOLATION / CRITICAL` on zone entry; suppressed while inside; uses `zone_evaluator.evaluate()` (Shapely polygons loaded from `shared/schemas/zones.json` at startup).
- `LowBatteryRule` — fires `LOW_BATTERY / WARNING` when battery < `warn_pct` (20%); clears when battery > `clear_pct` (25%) — hysteresis prevents oscillation.

**`app/services/command_service.py` — `CommandService`**
Handles emergency commands (`LAND`, `RTH`, `CUT_MOTORS`):
1. Verify agent exists in DB.
2. Write `CommandLog(status=SENT)` — durable before any attempt to send.
3. If gateway WS offline → `CommandLog(status=FAILED)`, return error.
4. Send `CommandDispatch` JSON over gateway WS; on failure → mark FAILED.
ACKs come back as `AckFrame` messages on the gateway WS and are handled in `ws.py::_handle_ack()`.

### Auth

Custom stdlib-only HS256 JWT in `app/auth/jwt.py` (no `python-jose` / `PyJWT` dependency). Gateway authenticates via `POST /gateways/auth` → `GET /ws/gateway/{hardware_id}?token=<JWT>`. The `authenticate_gateway_ws` function validates the token AND checks `token.sub == hardware_id` to prevent cross-gateway impersonation.

`POST /api/v1/auth/gateway-token` is a dev-only endpoint with no auth — it mints tokens freely.

### Gateway Package

**`GatewayClient`** runs three `asyncio.TaskGroup` tasks under one WS connection:
- **Task A (live producer):** `adapter.read_telemetry()` → `ws.send()`. On `ConnectionClosed`, saves the unsent frame to `OfflineBuffer` then raises.
- **Task B (buffer drainer):** Reads `OfflineBuffer.drain()`, injects `is_backfill=True`, sends. `asyncio.sleep(0)` after each frame yields the event loop to Task C.
- **Task C (command receiver):** `async for raw in ws` → `adapter.send_command()` → send ACK.

Tasks A and B share `asyncio.Lock(_send_lock)` to prevent interleaved WS writes.

**`OfflineBuffer`** is an `aiosqlite`-backed FIFO. Bounded by `max_size` (default 1000); evicts oldest rows on overflow. Must be used as an async context manager.

**`SimulatedDroneAdapter`** implements `AbstractDeviceAdapter`. Flies a circular orbit with configurable parameters. Reacts to commands: `LAND` → descent at 5 m/s, `RTH` → steers toward center then lands, `CUT_MOTORS` → altitude instantly 0.

### REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/api/v1/agents` | List all agents (DB) |
| GET | `/api/v1/agents/snapshot` | Live in-memory fleet state (no DB) |
| GET | `/api/v1/agents/{id}` | Single agent |
| GET | `/api/v1/agents/{id}/path` | Breadcrumbs with optional `from`/`to`/`limit` |
| GET | `/api/v1/agents/{id}/breadcrumbs` | All breadcrumbs for most recent session (ASC) |
| GET | `/api/v1/agents/{id}/sessions` | Flight sessions |
| GET | `/api/v1/zones` | Configured no-fly zones |
| GET | `/api/v1/violations` | Geofence violation log |
| POST | `/api/v1/auth/gateway-token` | Dev-only JWT mint |
| WS | `/ws/gateway/{hardware_id}` | Gateway connection |
| WS | `/ws/fleet/live` | Frontend connection |

### Frontend Architecture

**State management:** Single `useReducer` with `fleetReducer` — no Redux/Zustand. `AppState` holds `agents` (dict), `selectedAgentId`, `replay` (film mode), `alerts`, `wsStatus`. All actions are discriminated union `FleetAction` types.

**Dual provider pattern:**
- `MockFleetProvider` — two simulated drones at 2 Hz, full frame history in `historyRef`, `loadTrail()` returns recorded frames. Toggle via `VITE_USE_MOCK=true` or `?mock=true`.
- `RealFleetProvider` — connects `useFleetSocket`, `loadTrail()` fetches `/api/v1/agents/{id}/breadcrumbs`.

Both expose the same `FleetContext` shape: `{ state, dispatch, loadTrail }`.

**WebSocket (`useFleetSocket`):**
- Reconnects with exponential backoff (1s → doubles → 30s cap).
- On first connect: only dispatches `WS_STATUS=OPEN`.
- On *re*connect: also fires `GET /api/v1/agents/snapshot` → `SYNC_COMPLETE` so the map is correct immediately without waiting for the next `FLEET_UPDATE`.
- `isFirstConnect` ref distinguishes the two cases.

**Replay (Film Mode):**
- `REPLAY_ADVANCE` action is dispatched by a `setInterval` in `ReplayControls`'s `useEffect` — timer lives outside the reducer (reducer stays pure).
- `REPLAY_ADVANCE` auto-pauses at the end (`currentIndex >= frames.length - 1`).
- Speed options: 1×, 2×, 5×, 10× (interval = `base_ms / speedMultiplier`).

**Agent markers (`AgentMarker.tsx`):**
- Uses Leaflet `DivIcon` with inline SVG (drone/rover icons).
- `useMemo` deps: `[battery_pct, status, link_status, device_type, isSelected]` — intentionally omits `latitude/longitude` (position updates handled by `<Marker position={...}>` prop, not icon rebuild).
- Color: green (>25%), yellow (15-25%), red (≤15%), grey (STALE or not LINKED). Mirrors backend `clear_pct=25 / warn_pct=20` thresholds.

**Styling:** Tailwind CSS v4 (Vite plugin, `@import "tailwindcss"` in `index.css`). Leaflet CSS also imported in `index.css`. Custom `.agent-marker-*` classes for DivIcon.

### WebSocket Message Protocol

All messages have `msg_type` discriminator. Key types:

| Direction | `msg_type` | Description |
|-----------|-----------|-------------|
| Gateway→Backend | `TELEMETRY` | Position/battery frame; `is_backfill: bool` flag |
| Gateway→Backend | `LINK_STATUS` | Radio link change (`LINKED`/`RADIO_LOST`) |
| Gateway→Backend | `ACK` | Command acknowledgement |
| Backend→Gateway | `READY` | Session open confirmation with `agent_id`, `session_id` |
| Backend→Gateway | `COMMAND` | Emergency command dispatch |
| Frontend→Backend | `COMMAND` | Operator issues `LAND`/`RTH`/`CUT_MOTORS` |
| Backend→Frontend | `FLEET_UPDATE` | Full in-memory fleet snapshot (every frame) |
| Backend→Frontend | `ALERT` | Rule-triggered alert (`GEOFENCE_VIOLATION`/`LOW_BATTERY`) |
| Backend→Frontend | `COMMAND_SENT` | Command accepted and dispatched |
| Backend→Frontend | `COMMAND_ERROR` | Command could not be dispatched |

Schema version `"1.0"` on all MVP messages. Canonical JSON schemas in `shared/schemas/messages.json` and `shared/schemas/zones.json`.

### Database

PostgreSQL 16. All tables use UUID primary keys. Key tables:
- `gateways` — physical gateway devices; `hardware_id` unique.
- `agents` — one per `hardware_id`; upserted on each gateway connect; `device_type` (`DRONE`/`ROVER`).
- `flight_sessions` — opened on gateway WS connect, closed on disconnect.
- `gps_breadcrumbs` — throttled writes (≥2s event-time gap, or any alert on that frame). Indexed on `(agent_id, recorded_at)`.
- `command_logs` — audit trail; `status` flows `SENT → ACKNOWLEDGED/FAILED/REJECTED`.
- `violation_logs` — one row per geofence entry event.

Alembic migrations in `backend/alembic/versions/`. Run `alembic upgrade head` before first use.

### CI Pipeline (`.github/workflows/ci.yml`)

Three jobs, all on `ubuntu-latest`:
1. **backend-lint** — `ruff check` + `black --check` (no DB needed)
2. **backend-test** — needs `backend-lint`; spins up `postgres:16-alpine`; runs `alembic upgrade head` then `pytest`
3. **frontend-lint** — `npm ci` (strict, no `--legacy-peer-deps`) + `tsc --noEmit` + `eslint`

Frontend uses React 18.3.1. `react-leaflet` must stay at `^4.x` — v5 requires React 19.

## Key Design Decisions

- **Event-time throttle for breadcrumbs:** The persist throttle measures `frame.timestamp` (drone time), not `datetime.now()` (server time). This is essential for buffer replay: a burst of 1000 buffered frames arriving in 1 second would collapse to a single breadcrumb if using server clock.
- **is_backfill flag:** Set by `GatewayClient` when draining `OfflineBuffer`. Backend uses it to skip rules/alerts/broadcast/`last_seen_at` update so stale data doesn't pollute live state.
- **Broadcaster stale-frame guard:** `update_agent()` drops any frame where `frame.last_seen_at <= current.last_seen_at`. Prevents buffer drain from overwriting a more-recent live frame.
- **RulesEngine & FleetBroadcaster as singletons:** Created via `@lru_cache(maxsize=1)` in `dependencies.py`; shared across all WS connections.
- **`asyncio.Lock` for concurrent WS sends:** Tasks A and B in `GatewayClient` both call `ws.send()`. The lock prevents interleaved frames that would corrupt the WebSocket framing.
- **Custom stdlib JWT:** Avoids `cryptography` native extension dependency issues. HS256 only, timing-safe compare via `hmac.compare_digest`.
- **Watchdog timer:** Backend closes gateway WS with code 4408 if no frames received for `watchdog_timeout_seconds=20`. Gateway has a heartbeat interval; watchdog is 2× that.
