# SYSTEM_DESIGN.md — The Secure Fleet Commander

> **This file is the canonical source of truth for the project.**
> All architectural decisions, schemas, and contracts live here first.
> Code must conform to this document, not the other way around.
> The Decision Log (§9) is append-only — never delete a row.

---

## 1. MVP Scope & Constraints

### System Philosophy: Safety Monitor

The system is a **Safety Monitor**, not a flight management system. The drone is operated locally by a human pilot. This backend provides real-time constraint enforcement and emergency override capability only.

- **The pilot flies the drone.** This system does not plan, schedule, or control missions.
- **The backend monitors.** It checks every telemetry frame against geofence and battery constraints.
- **Operators override.** The frontend provides emergency controls, not mission planning.

### In Scope (MVP)
- A **Gateway** process that connects to a physical or simulated drone, normalises data to a 6-field telemetry frame, and streams it to the Backend over an authenticated WebSocket.
- A **Backend** (FastAPI) that ingests telemetry, persists it, evaluates geofence and battery rules, and fans out live data + alerts to connected Frontend clients.
- A **Frontend** (React) that renders all active agents on a map, shows link status and staleness, and lets operators issue emergency overrides.
- **Three emergency override commands**: `LAND`, `RTH` (Return To Home), `CUT_MOTORS` — bi-directional, acknowledged. No parameters; the drone's local autopilot executes them.
- **Two policy rules**: No-Fly Zone (geofence) and Low Battery — both log violations and push alerts. No automated command in MVP.

### Explicitly Deferred
| Feature | Reason |
|---|---|
| mTLS between Gateway and Backend | JWT is sufficient to prove the auth pattern; mTLS adds PKI complexity |
| User accounts / RBAC | Not needed until multi-operator scenario |
| Auto-command on geofence breach | Logging the violation proves the evaluator; auto-RTH is next milestone |
| Full policy DSL | Over-engineering before we know the rule shape |
| Delta compression / PostGIS LineString | Premature optimisation; breadcrumbs prove the pattern |
| TimescaleDB hypertables | Plain PostgreSQL table with index is sufficient for MVP load |
| Waypoint / mission planning | Out of scope — pilot controls flight path locally |

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
        RULES[Rules Engine\nGeofence + Low Battery]
        VLOG[ViolationLog Writer]
        CMD[Emergency Command Dispatcher\nLAND | RTH | CUT_MOTORS]
        REST[REST API]
        ORM[SQLAlchemy ORM]
        PG[(PostgreSQL)]
        WS_FE[Frontend WebSocket\n/ws/fleet/live]

        WS_GW --> INGEST
        INGEST --> ORM
        INGEST --> RULES
        RULES --> GEO
        GEO -->|violation| VLOG
        VLOG --> ORM
        CMD --> WS_GW
        REST --> ORM
        ORM --> PG
        INGEST -->|fan-out| WS_FE
        RULES -->|alert| WS_FE
    end

    subgraph FRONTEND ["Frontend (React)"]
        MAP[Leaflet Map\nAll active agents]
        HB[Heartbeat Monitor\nLink status indicator]
        PANEL[Agent Panel\nStats + Emergency Controls]
        WS_CLI[WebSocket Client]

        WS_CLI --> MAP
        WS_CLI --> HB
        MAP -->|click| PANEL
        PANEL -->|LAND / RTH / CUT_MOTORS| WS_CLI
    end

    TUNNEL <-->|WSS + JWT| WS_GW
    WS_FE <-->|WSS| WS_CLI
    REST <-->|HTTPS| FRONTEND
```

### Layer Responsibilities (one sentence each)
| Layer | Responsibility |
|---|---|
| **Gateway** | Translate raw device protocol to 6-field JSON, buffer when offline, authenticate and stream to Backend. No business logic. |
| **Ingestion Service** | Validate the inbound frame, write breadcrumb + update `last_seen_at`, trigger rules evaluation, fan-out to frontend. |
| **No-Fly Zone Evaluator** | Pure function — `(lat, lon, zones[]) → bool`. Side-effectless; caller writes the `ViolationLog`. |
| **Emergency Command Dispatcher** | Receive `LAND / RTH / CUT_MOTORS` from frontend WS, validate, write `CommandLog`, push `COMMAND_DISPATCH` to Gateway WS. |
| **Frontend** | Display live fleet state, show link/battery status, surface emergency override buttons on agent click. |

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
Gateway (1) ──< Agent (N) ──< FlightSession (1) ──< GpsBreadcrumb (N)
Agent (1) ──< CommandLog (N)
Agent (1) ──< ViolationLog (N)
```

### 3.2 Model Definitions

#### `gateways`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `default=uuid4` |
| hardware_id | TEXT UNIQUE NOT NULL | Physical gateway device fingerprint |
| display_name | TEXT NOT NULL | Human-readable label |
| registered_at | TIMESTAMPTZ | `default=utcnow` |
| last_connected_at | TIMESTAMPTZ nullable | Updated on every WS connect |

#### `agents`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `default=uuid4` |
| hardware_id | TEXT UNIQUE NOT NULL | Physical device fingerprint (e.g. FC MAC) |
| display_name | TEXT NOT NULL | Human-readable label |
| device_type | TEXT NOT NULL | Default: `"DRONE"` |
| registered_at | TIMESTAMPTZ | `default=utcnow` |
| last_seen_at | TIMESTAMPTZ nullable | Updated on every telemetry frame |
| gateway_id | UUID FK→gateways nullable | Which gateway is relaying this agent's telemetry |
| link_status | TEXT NOT NULL | `LINKED \| RADIO_LOST \| CLOUD_LOST` — default `LINKED` |

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
| session_id | UUID FK→flight_sessions | NOT NULL — explicitly links each point to a session |
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
| command_type | TEXT(20) NOT NULL | `LAND \| RTH \| CUT_MOTORS` |
| payload | JSONB NOT NULL | `{}` — emergency commands carry no coordinate parameters |
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

-- Agents by gateway (bulk update on disconnect)
CREATE INDEX idx_agents_gateway ON agents (gateway_id);
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

### 4.2 `COMMAND` — Frontend → Backend (`/ws/fleet/live`)

Emergency override commands only. No coordinate parameters — the drone's local autopilot handles execution.

```json
{
  "msg_type": "COMMAND",
  "command_type": "LAND",
  "agent_id": "<uuid>"
}
```

Valid `command_type` values: `LAND | RTH | CUT_MOTORS`

### 4.3 `COMMAND_DISPATCH` — Backend → Gateway (`/ws/gateway/{hardware_id}`)

```json
{
  "msg_type": "COMMAND",
  "command_id": "<uuid>",
  "command_type": "LAND",
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
      "status": "ONLINE",
      "link_status": "LINKED"
    }
  ]
}
```

`status` values: `ONLINE | STALE` (computed server-side from `last_seen_at` recency)
`link_status` values: `LINKED | RADIO_LOST | CLOUD_LOST` (set by protocol events — see §4.7)

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

### 4.7 `LINK_STATUS` — Gateway → Backend

Sent when the gateway detects a change in its radio link to a field agent. The gateway's cloud WebSocket remains connected; only the field radio link changed.

```json
{
  "msg_type": "LINK_STATUS",
  "agent_id": "<uuid>",
  "link_status": "RADIO_LOST",
  "detected_at": "<ISO-8601 UTC>"
}
```

Valid `link_status` values: `LINKED | RADIO_LOST`

**Disconnect taxonomy:**

| Event | Who detects | How backend knows | `link_status` result |
|---|---|---|---|
| Field radio failure | Gateway (radio timeout) | `LINK_STATUS` message | `RADIO_LOST` |
| Gateway WS drop | Backend (disconnect exception) | WS disconnect handler | `CLOUD_LOST` for all agents on that gateway |

### 4.8 Schema Versioning Policy
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

## 9. Decision Log

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
| 13 | 2026-05-03 | Separate Gateway model from Agent; add `link_status` (LINKED/RADIO_LOST/CLOUD_LOST) | Derive disconnect type from `last_seen_at` alone | Cloud disconnect (WS drop) and field disconnect (radio loss) have different operational responses; conflating them via timestamp forces operators to guess the cause |
| 14 | 2026-05-03 | Replace `GO_TO_WAYPOINT` with `LAND \| RTH \| CUT_MOTORS`; drop waypoint/mission planning | Keep GO_TO_WAYPOINT as the one command | System is a Safety Monitor: pilot controls flight path locally; backend only enforces constraints and provides emergency override; navigation commands create liability if backend state diverges from physical state |
