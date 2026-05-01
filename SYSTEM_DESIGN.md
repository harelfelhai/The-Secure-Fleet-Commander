# SYSTEM_DESIGN.md — The Secure Fleet Commander

> **This file is the canonical source of truth for the project.**
> All architectural decisions, schemas, and contracts live here first.
> Code must conform to this document, not the other way around.
> The Decision Log (§8) is append-only — never delete a row.

---

## 1. MVP Scope & Constraints

### In Scope (MVP)
- A **Gateway** process that connects to a physical or simulated drone, normalises data to a 6-field telemetry frame, and streams it to the Backend over an authenticated WebSocket.
- A **Backend** (FastAPI) that ingests telemetry, persists it, evaluates a No-Fly Zone rule, and fans out live data to connected Frontend clients.
- A **Frontend** (React) that renders all active agents on a map, shows a heartbeat-based staleness indicator, and lets operators send a single `GO_TO_WAYPOINT` command via click-to-interact.
- **One command**: `GO_TO_WAYPOINT` — bi-directional, acknowledged.
- **One policy rule**: No-Fly Zone point-in-polygon check — logs a violation on breach; no auto-command in MVP.

### Explicitly Deferred
| Feature | Reason |
|---|---|
| mTLS between Gateway and Backend | JWT is sufficient to prove the auth pattern; mTLS adds PKI complexity |
| User accounts / RBAC | Not needed until multi-operator scenario |
| Auto-command on geofence breach | Logging the violation proves the evaluator; auto-RTH is next milestone |
| Additional commands (RTH, ARM, LAND) | Adding a second command is trivial once the command pipeline exists |
| Full policy DSL | Over-engineering before we know the rule shape |
| Delta compression / PostGIS LineString | Premature optimisation; breadcrumbs prove the pattern |
| TimescaleDB hypertables | Plain PostgreSQL table with index is sufficient for MVP load |

---

## 2. Architecture Overview

```mermaid
graph TB
    subgraph EDGE ["Edge Layer (Gateway)"]
        SRC[MAVLink / Simulated Source]
        ADAPTER[DeviceAdapter\nNormalises to 6-field JSON]
        BUFFER[Offline Buffer\nSQLite Priority Queue]
        TUNNEL[WSS Tunnel\nJWT Auth]

        SRC --> ADAPTER
        ADAPTER --> BUFFER
        BUFFER --> TUNNEL
    end

    subgraph BACKEND ["Backend (FastAPI)"]
        WS_GW[Gateway WebSocket\n/ws/gateway/{hardware_id}]
        INGEST[Ingestion Service\nValidate → Persist → Evaluate]
        GEO[No-Fly Zone Evaluator\nShapely point-in-polygon]
        VLOG[ViolationLog Writer]
        CMD[Command Dispatcher\nGO_TO_WAYPOINT only]
        REST[REST API]
        ORM[SQLAlchemy ORM]
        PG[(PostgreSQL)]
        WS_FE[Frontend WebSocket\n/ws/fleet/live]

        WS_GW --> INGEST
        INGEST --> ORM
        INGEST --> GEO
        GEO -->|violation| VLOG
        VLOG --> ORM
        CMD --> WS_GW
        REST --> ORM
        ORM --> PG
        INGEST -->|fan-out| WS_FE
    end

    subgraph FRONTEND ["Frontend (React)"]
        MAP[Leaflet Map\nAll active agents]
        HB[Heartbeat Monitor\nGray icon after Xs]
        PANEL[Agent Panel\nStats + GO_TO form]
        WS_CLI[WebSocket Client]

        WS_CLI --> MAP
        WS_CLI --> HB
        MAP -->|click| PANEL
        PANEL -->|GO_TO_WAYPOINT| WS_CLI
    end

    TUNNEL <-->|WSS + JWT| WS_GW
    WS_FE <-->|WSS| WS_CLI
    REST <-->|HTTPS| FRONTEND
```

### Layer Responsibilities (one sentence each)
| Layer | Responsibility |
|---|---|
| **Gateway** | Translate raw device protocol to 6-field JSON, buffer when offline, authenticate and stream to Backend. No business logic. |
| **Ingestion Service** | Validate the inbound frame, write breadcrumb + update `last_seen_at`, trigger zone evaluation, fan-out to frontend. |
| **No-Fly Zone Evaluator** | Pure function — `(lat, lon, zones[]) → bool`. Side-effectless; caller writes the `ViolationLog`. |
| **Command Dispatcher** | Receive `GO_TO_WAYPOINT` from frontend WS, validate, write `CommandLog`, push `COMMAND_DISPATCH` to Gateway WS. |
| **Frontend** | Display live fleet state, dim stale agents, surface a command form on agent click. |

### Technology Choices
| Component | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI + Python 3.11 | Async-native, automatic OpenAPI, Pydantic v2 built-in |
| ORM | SQLAlchemy 2.x (async) | Mature, type-safe, pairs well with Alembic |
| DB | PostgreSQL 16 | JSONB, strong geospatial extension path, production-proven |
| Zone evaluation | Shapely 2.x | Pure Python, no DB extension needed in MVP |
| Frontend | React 18 + TypeScript + Vite | Fast DX, strong typing, large ecosystem |
| Map | Leaflet + react-leaflet | Lightweight, open-source tiles, easy marker control |
| State | Zustand | Minimal boilerplate, fine-grained subscriptions |
| Gateway comms | asyncio + websockets | Matches Backend async model |
| Offline buffer | SQLite (aiosqlite) | Zero-config, survives process restart |

---

## 3. Data Architecture

### 3.1 Entity Relationship

```
Agent (1) ──< FlightSession (1) ──< GpsBreadcrumb (N)
Agent (1) ──< CommandLog (N)
Agent (1) ──< ViolationLog (N)
```

### 3.2 Model Definitions

#### `agents`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `default=uuid4` |
| hardware_id | TEXT UNIQUE NOT NULL | Physical device fingerprint (e.g. FC MAC) |
| display_name | TEXT NOT NULL | Human-readable label |
| device_type | TEXT NOT NULL | Default: `"DRONE"` |
| registered_at | TIMESTAMPTZ | `default=utcnow` |
| last_seen_at | TIMESTAMPTZ nullable | Updated on every telemetry frame |

#### `flight_sessions`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_id | UUID FK→agents | NOT NULL |
| started_at | TIMESTAMPTZ | NOT NULL |
| ended_at | TIMESTAMPTZ nullable | NULL = session still active |

#### `gps_breadcrumbs`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK→flight_sessions | NOT NULL |
| agent_id | UUID FK→agents | Denormalised for query speed |
| recorded_at | TIMESTAMPTZ | NOT NULL |
| latitude | DOUBLE PRECISION | NOT NULL |
| longitude | DOUBLE PRECISION | NOT NULL |
| altitude_m | DOUBLE PRECISION | NOT NULL |
| battery_pct | DOUBLE PRECISION | NOT NULL |

#### `command_logs`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_id | UUID FK→agents | NOT NULL |
| command_type | TEXT NOT NULL | MVP: `"GO_TO_WAYPOINT"` only |
| payload | JSONB NOT NULL | `{"latitude": ..., "longitude": ..., "altitude_m": ...}` |
| status | TEXT | `SENT \| ACKNOWLEDGED \| FAILED \| TIMEOUT` |
| issued_at | TIMESTAMPTZ | `default=utcnow` |
| acked_at | TIMESTAMPTZ nullable | |

#### `violation_logs`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| agent_id | UUID FK→agents | NOT NULL |
| zone_name | TEXT NOT NULL | |
| latitude | DOUBLE PRECISION | NOT NULL |
| longitude | DOUBLE PRECISION | NOT NULL |
| detected_at | TIMESTAMPTZ | `default=utcnow` |

### 3.3 Indexes
```sql
-- Primary read pattern: flight path for agent X in time range Y
CREATE INDEX idx_breadcrumbs_agent_time ON gps_breadcrumbs (agent_id, recorded_at DESC);

-- Active session lookup
CREATE INDEX idx_sessions_agent_active ON flight_sessions (agent_id) WHERE ended_at IS NULL;

-- Command history per agent
CREATE INDEX idx_commands_agent ON command_logs (agent_id, issued_at DESC);
```

### 3.4 Alembic Strategy
- One migration per milestone that touches the schema.
- Never edit a committed migration; always add a new one.
- `alembic upgrade head` is idempotent and runs automatically in the dev Docker entrypoint.

---

## 4. Message Contract

> All messages are JSON objects sent over WebSocket. The `msg_type` field is the discriminator.
> `schema_version` is `"1.0"` for all MVP messages.

### 4.1 `TELEMETRY` — Gateway → Backend

```json
{
  "msg_type": "TELEMETRY",
  "schema_version": "1.0",
  "agent_id": "<uuid>",
  "timestamp": "<ISO-8601 UTC>",
  "latitude": 32.0853,
  "longitude": 34.7818,
  "altitude_m": 120.5,
  "battery_pct": 74.2
}
```

> `agent_id` here is the UUID issued by the Backend on first registration. The Gateway stores it after the handshake.

### 4.2 `GO_TO_WAYPOINT` — Frontend → Backend (`/ws/fleet/live`)

```json
{
  "msg_type": "COMMAND",
  "command_type": "GO_TO_WAYPOINT",
  "agent_id": "<uuid>",
  "payload": {
    "latitude": 32.09,
    "longitude": 34.78,
    "altitude_m": 50.0
  }
}
```

### 4.3 `COMMAND_DISPATCH` — Backend → Gateway (`/ws/gateway/{hardware_id}`)

```json
{
  "msg_type": "COMMAND",
  "command_id": "<uuid>",
  "command_type": "GO_TO_WAYPOINT",
  "payload": {
    "latitude": 32.09,
    "longitude": 34.78,
    "altitude_m": 50.0
  },
  "issued_at": "<ISO-8601 UTC>"
}
```

### 4.4 `ACK` — Gateway → Backend

```json
{
  "msg_type": "ACK",
  "command_id": "<uuid>",
  "status": "ACKNOWLEDGED",
  "acked_at": "<ISO-8601 UTC>"
}
```

Valid `status` values: `ACKNOWLEDGED | FAILED | REJECTED`

### 4.5 `FLEET_UPDATE` — Backend → Frontend (fan-out on every telemetry frame)

```json
{
  "msg_type": "FLEET_UPDATE",
  "agents": [
    {
      "agent_id": "<uuid>",
      "display_name": "Alpha-1",
      "latitude": 32.0853,
      "longitude": 34.7818,
      "altitude_m": 120.5,
      "battery_pct": 74.2,
      "last_seen_at": "<ISO-8601 UTC>",
      "status": "ONLINE"
    }
  ]
}
```

`status` is computed server-side: `ONLINE` if `(now - last_seen_at) < HEARTBEAT_TIMEOUT_SECONDS`, else `STALE`.

### 4.6 `ALERT` — Backend → Frontend

Unified alert message covering all rule-triggered events. `alert_type` discriminates the event;
`context` carries type-specific fields. Replaces the narrower `VIOLATION_ALERT` from the initial design
(see Decision Log row 8).

```json
{
  "msg_type": "ALERT",
  "alert_type": "GEOFENCE_VIOLATION | LOW_BATTERY",
  "severity": "WARNING | CRITICAL",
  "agent_id": "<uuid>",
  "message": "Human-readable description",
  "context": {
    "zone_name": "Restricted Airspace Alpha"
  },
  "detected_at": "<ISO-8601 UTC>"
}
```

**`GEOFENCE_VIOLATION` context fields**: `zone_name: str`
**`LOW_BATTERY` context fields**: `battery_pct: float`, `threshold_pct: float`

### 4.7 Schema Versioning Policy
- The `schema_version` field is checked on every inbound frame. Unknown versions are rejected with a `400`-equivalent WS close code.
- Minor additions (new optional fields) increment the minor version: `"1.1"`.
- Breaking changes increment the major version and require a migration plan.

---

## 5. No-Fly Zone Evaluator

### Algorithm
```
for each zone in zones:
    if shapely.contains(zone.polygon, Point(lon, lat)):
        return (True, zone.name)
return (False, None)
```

Uses `shapely.geometry.Point` and `shapely.geometry.Polygon`. Coordinate order is `(longitude, latitude)` per GeoJSON convention — **not** `(lat, lon)`.

### Config Loading
Loaded once at Backend startup from `shared/schemas/zones.json`. Parsed into `shapely.Polygon` objects and held in memory. Restart required to pick up zone changes (acceptable for MVP).

### MVP Response to Violation
Edge-triggered: fires once on zone entry, suppressed while the agent remains inside (dedup via
`RuleContext.active_zones`). Clears when the agent leaves. On breach: write a `ViolationLog` row
and push an `ALERT` (type `GEOFENCE_VIOLATION`) to all frontend WebSocket clients. No automated command issued.

---

## 6. Heartbeat Timeout

**Threshold**: `HEARTBEAT_TIMEOUT_SECONDS = 10` (defined as a single constant in `backend/app/config.py`).

**Computation**: Client-side, on a 1-second `setInterval` tick. For each agent in Zustand store: if `(Date.now() - Date.parse(last_seen_at)) > threshold * 1000` → render grayed-out marker.

**Rationale for client-side**: Reduces backend load; avoids a separate status-push channel; client clock drift of <1 s is acceptable for a visual staleness indicator.

The `status` field in `FLEET_UPDATE` messages is also computed server-side (for REST consumers and future alerting), but the Frontend uses its own clock for the map icon.

---

## 7. Rules Engine

### Rule Interface
```python
class Rule(ABC):
    name: str
    def evaluate(self, frame: TelemetryFrame, ctx: RuleContext) -> list[InternalAlert]: ...
```

### RuleContext (per-agent, owned by RulesEngine)
| Field | Type | Purpose |
|---|---|---|
| `prior_battery_pct` | `float \| None` | Updated by engine after all rules run; used for edge detection |
| `active_zones` | `set[str]` | Zone names the agent is currently inside; prevents duplicate alerts |
| `low_battery_active` | `bool` | True while battery is below warn threshold; enforces hysteresis |

### Implemented Rules (Milestone 1)
| Rule | Trigger | Dedup strategy | Persisted? |
|---|---|---|---|
| `GeofenceRule` | Agent enters a no-fly zone polygon | Entry-only; suppressed while inside | Yes — `ViolationLog` row |
| `LowBatteryRule` | Battery drops below `BATTERY_WARN_PCT` (20%) | Edge-triggered; clears at `BATTERY_CLEAR_PCT` (25%) | No — transient UI alert |

### Engine Lifecycle
1. `RulesEngine.evaluate(frame)` runs all rules in order, collecting `InternalAlert` objects.
2. If a rule raises, the exception is logged; other rules continue (fail-open).
3. `ctx.prior_battery_pct` is updated **after** all rules have run (so each rule sees the same prior value).
4. `clear_agent_state(agent_id)` is called on disconnect to reset dedup state for next session.

---

## 8. Extensibility Contract

### AbstractDeviceAdapter
Any new device type implements exactly one class:

```python
class AbstractDeviceAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def read_telemetry(self) -> TelemetryFrame: ...
    # Returns a validated TelemetryFrame (the 6-field schema).
    # All device-specific parsing happens inside this method.

    @abstractmethod
    async def send_command(self, command: CommandDispatch) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
```

### How to Add a New Device Type
1. Create `gateway/app/adapters/<device_type>_adapter.py`.
2. Implement `AbstractDeviceAdapter`.
3. Map the new `device_type` string to your class in `gateway/app/adapter_registry.py`.
4. Add unit tests for `read_telemetry` and `send_command`.
5. No changes to core Gateway loop, Backend, or Frontend required.

---

## 8. Decision Log

| # | Date | Decision | Alternatives Considered | Rationale |
|---|---|---|---|---|
| 1 | 2026-05-01 | Alert/policy logic lives in Backend, not Gateway | Gateway-side alerts | Gateway stays dumb; single intelligence surface; easier to test |
| 2 | 2026-05-01 | No-Fly Zones loaded from static `zones.json` at startup | DB table with CRUD API | Avoids premature schema complexity; trivial to migrate later |
| 3 | 2026-05-01 | Heartbeat staleness computed client-side | Server-side `STALE` push | Reduces backend load; visual UI concern belongs in the client |
| 4 | 2026-05-01 | JWT auth for MVP (not mTLS) | mTLS from day one | mTLS requires PKI setup; JWT proves the auth pattern in 1/10th the time |
| 5 | 2026-05-01 | Commands via WebSocket, not REST POST | REST POST → poll for status | WebSocket is already open; avoids HTTP round-trip + polling complexity |
| 6 | 2026-05-01 | Plain PostgreSQL table for breadcrumbs (no TimescaleDB) | TimescaleDB hypertable | Adds operational complexity before we know the ingestion rate |
| 7 | 2026-05-01 | Violation response = log only (no auto-command) | Auto-RTH on breach | Proves the evaluator safely; auto-command added once the command pipeline is validated |
| 8 | 2026-05-01 | Generalise `VIOLATION_ALERT` → `ALERT` with `alert_type` discriminator | Separate message type per rule | Single message type scales to any number of rules; frontend handles one shape |
| 9 | 2026-05-01 | Add `LowBatteryRule` to Milestone 1 | Defer to Milestone 3 | Two rules proves the engine's extensibility with zero extra infrastructure cost |
| 10 | 2026-05-01 | Geofence + low-battery alerts are edge-triggered with dedup | Alert every frame | At 1 Hz a non-deduped alert would produce 3600 rows/hour per agent inside a zone |
| 11 | 2026-05-01 | Low-battery alerts not persisted (transient UI only) | New `alert_logs` table | Avoids schema churn; ViolationLog covers the compliance-relevant case |
| 12 | 2026-05-01 | JWT implemented with stdlib hmac/hashlib (no PyJWT/jose) | PyJWT or python-jose | Both pull in `cryptography` which has broken native extensions in some environments; HS256 is trivial to implement correctly with stdlib |

---

## 9. Testing Strategy

### Unit Tests (no I/O)
- `NoFlyZoneEvaluator`: point inside zone, point outside zone, point on boundary, multiple zones.
- `TelemetryFrame` Pydantic schema: valid frame, missing field, wrong type, future timestamp.
- `MavlinkDroneAdapter` / `SimulatedDroneAdapter`: output conforms to `TelemetryFrame` schema.
- Offline buffer: FIFO ordering, drain sequence, persistence across restart.

### Integration Tests (real DB, test containers)
- Telemetry ingest: POST 10 frames → assert 10 `GpsBreadcrumb` rows, `Agent.last_seen_at` updated.
- Session lifecycle: WS connect → session opened; WS disconnect → `ended_at` set.
- Command round-trip: frontend WS sends `GO_TO_WAYPOINT` → `CommandLog` row `SENT` → simulated Gateway ACK → status `ACKNOWLEDGED`.
- Violation detection: frame inside zone → `ViolationLog` row written + `VIOLATION_ALERT` pushed to frontend WS client.

### E2E Smoke Test
- Start Simulator + Backend + Frontend.
- Assert agent marker appears on map within 3 seconds.
- Click marker, submit `GO_TO_WAYPOINT` → assert `CommandLog` row with status `SENT`.

---

## 10. Local Dev Setup

### Prerequisites
- Docker + Docker Compose v2
- Python 3.11+
- Node.js 20+

### Start the Stack
```bash
# 1. Start PostgreSQL
cd infra && docker compose up -d

# 2. Install backend deps and run migrations
cd backend
pip install -e ".[dev]"
alembic upgrade head

# 3. Start backend
uvicorn app.main:app --reload --port 8000

# 4. Start gateway simulator
cd gateway
pip install -e ".[dev]"
python -m app.main --mode simulate

# 5. Start frontend
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Environment Variables
Copy `backend/.env.example` to `backend/.env` and adjust:
```
DATABASE_URL=postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_commander
JWT_SECRET=change-me-in-development
HEARTBEAT_TIMEOUT_SECONDS=10
ZONES_CONFIG_PATH=../shared/schemas/zones.json
DEBUG=true
```
