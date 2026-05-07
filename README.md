# The Secure Fleet Commander

A modular Command & Control (C2) system for managing fleets of autonomous agents (drones, rovers, IoT). Private, self-hosted — no third-party cloud.

> **Architecture reference:** See [`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md) for the full system design, data schema, message contracts, and decision log.

---

## Project Structure

```
.
├── SYSTEM_DESIGN.md          # Canonical architecture reference
├── infra/
│   └── docker-compose.yml    # PostgreSQL + pgAdmin
├── shared/
│   └── schemas/
│       ├── messages.json     # Canonical WS message schemas
│       └── zones.json        # No-fly zone configuration
├── backend/                  # FastAPI backend (Python 3.11)
├── gateway/                  # Edge process — device adapter + WS tunnel
└── frontend/                 # React dashboard (TypeScript)
```

---

## Local Development Setup

### Prerequisites

- Docker + Docker Compose v2
- Python 3.11+
- Node.js 20+

### 1. Start the database

```bash
cd infra
docker compose up -d
```

PostgreSQL is available at `localhost:5432`.
pgAdmin UI is at [http://localhost:5050](http://localhost:5050) (admin@fleet.local / admin).

### 2. Set up the backend

```bash
cd backend
cp .env.example .env          # adjust if needed
pip install -e ".[dev]"
alembic upgrade head           # creates all tables
uvicorn app.main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
Health check: [http://localhost:8000/health](http://localhost:8000/health)

### 3. Run backend tests

```bash
cd backend
pytest -v
```

### 4. Start the gateway simulator

```bash
cd gateway
pip install -e ".[dev]"
python -m app.main
```

The gateway connects to the backend, registers as `sim-drone-001`, and begins streaming telemetry at 5 Hz.

### 5. Start the frontend

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173
```

To run without a backend (mock mode):

```bash
VITE_USE_MOCK=true npm run dev
# or open: http://localhost:5173?mock=true
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_commander` | Async PostgreSQL DSN |
| `JWT_SECRET` | `change-me-in-development` | HMAC secret for JWT tokens |
| `HEARTBEAT_TIMEOUT_SECONDS` | `10` | Seconds before an agent is marked STALE |
| `ZONES_CONFIG_PATH` | `../shared/schemas/zones.json` | Path to no-fly zones config |
| `DEBUG` | `false` | Enables SQLAlchemy query logging |

---

## Milestone Status

| Milestone | Status | Description |
|---|---|---|
| 0 — Foundation | ✅ Done | Repo structure, DB, backend skeleton, CI |
| 1 — Backend Ingest | ✅ Done | WebSocket ingest, persistence, zone evaluator, rules engine |
| 2 — Command Flow | ✅ Done | LAND / RTH / CUT_MOTORS pipeline, ACK handling |
| 3 — Gateway Simulator | ✅ Done | Simulated drone adapter, offline buffer, reconnect backoff |
| 4 — Frontend MVP | ✅ Done | Live map, agent markers, emergency controls, replay, no-fly zones |
| 5 — Hardening | 🔲 Pending | mTLS, rate limiting, structured logging |
