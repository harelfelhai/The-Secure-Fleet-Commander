import { describe, it, expect } from "vitest";
import { fleetReducer, initialState } from "./fleet.reducer";
import type { AgentState, TrailPoint, ZonePolygon } from "../types/fleet";

function makeAgent(overrides: Partial<AgentState> = {}): AgentState {
  return {
    agent_id: "agent-1",
    display_name: "Alpha",
    device_type: "DRONE",
    latitude: 32.0,
    longitude: 34.7,
    altitude_m: 50,
    battery_pct: 80,
    last_seen_at: "2024-01-01T00:00:00Z",
    mission_start_at: null,
    status: "ONLINE",
    link_status: "LINKED",
    ...overrides,
  };
}

function makeTrailPoint(index: number): TrailPoint {
  return {
    latitude: 32.0 + index * 0.001,
    longitude: 34.7,
    altitude_m: 50,
    battery_pct: 80,
    recorded_at: `2024-01-01T00:0${index}:00Z`,
  };
}

describe("fleetReducer", () => {
  // ── FLEET_UPDATE / SYNC_COMPLETE ──────────────────────────────────────────

  it("FLEET_UPDATE replaces agents dict", () => {
    const agent = makeAgent();
    const state = fleetReducer(initialState, {
      type: "FLEET_UPDATE",
      payload: [agent],
    });
    expect(state.agents).toEqual({ "agent-1": agent });
  });

  it("SYNC_COMPLETE behaves identically to FLEET_UPDATE", () => {
    const agent = makeAgent();
    const fromUpdate = fleetReducer(initialState, {
      type: "FLEET_UPDATE",
      payload: [agent],
    });
    const fromSync = fleetReducer(initialState, {
      type: "SYNC_COMPLETE",
      payload: [agent],
    });
    expect(fromSync.agents).toEqual(fromUpdate.agents);
    expect(fromSync.batteryHistory).toEqual(fromUpdate.batteryHistory);
  });

  it("FLEET_UPDATE accumulates battery history", () => {
    let state = initialState;
    for (let i = 0; i < 3; i++) {
      state = fleetReducer(state, {
        type: "FLEET_UPDATE",
        payload: [makeAgent({ battery_pct: 80 - i * 10 })],
      });
    }
    expect(state.batteryHistory["agent-1"]).toEqual([80, 70, 60]);
  });

  it("battery history caps at 60 entries", () => {
    let state = initialState;
    for (let i = 0; i < 70; i++) {
      state = fleetReducer(state, {
        type: "FLEET_UPDATE",
        payload: [makeAgent({ battery_pct: i % 100 })],
      });
    }
    expect(state.batteryHistory["agent-1"]).toHaveLength(60);
  });

  // ── ZONES_LOADED ─────────────────────────────────────────────────────────

  it("ZONES_LOADED stores zones", () => {
    const zones: ZonePolygon[] = [
      { name: "Zone A", latlngs: [[32.0, 34.7], [32.1, 34.7], [32.1, 34.8]] },
    ];
    const state = fleetReducer(initialState, { type: "ZONES_LOADED", payload: zones });
    expect(state.zones).toEqual(zones);
  });

  // ── REPLAY_ADVANCE ────────────────────────────────────────────────────────

  it("REPLAY_ADVANCE increments currentIndex", () => {
    const frames = [makeTrailPoint(0), makeTrailPoint(1), makeTrailPoint(2)];
    const withReplay = fleetReducer(initialState, {
      type: "REPLAY_LOADED",
      payload: { agentId: "agent-1", frames },
    });
    const advanced = fleetReducer(withReplay, { type: "REPLAY_ADVANCE" });
    expect(advanced.replay.currentIndex).toBe(1);
  });

  it("REPLAY_ADVANCE auto-pauses at last frame", () => {
    const frames = [makeTrailPoint(0), makeTrailPoint(1)];
    let state = fleetReducer(initialState, {
      type: "REPLAY_LOADED",
      payload: { agentId: "agent-1", frames },
    });
    state = fleetReducer(state, { type: "REPLAY_PLAY" });
    // Advance to last frame
    state = fleetReducer(state, { type: "REPLAY_ADVANCE" });
    expect(state.replay.currentIndex).toBe(1);
    // One more advance should pause at last frame
    state = fleetReducer(state, { type: "REPLAY_ADVANCE" });
    expect(state.replay.currentIndex).toBe(1);
    expect(state.replay.isPlaying).toBe(false);
  });

  // ── REPLAY_SEEK ───────────────────────────────────────────────────────────

  it("REPLAY_SEEK clamps to valid range (low)", () => {
    const frames = [makeTrailPoint(0), makeTrailPoint(1), makeTrailPoint(2)];
    let state = fleetReducer(initialState, {
      type: "REPLAY_LOADED",
      payload: { agentId: "agent-1", frames },
    });
    state = fleetReducer(state, { type: "REPLAY_SEEK", payload: -5 });
    expect(state.replay.currentIndex).toBe(0);
  });

  it("REPLAY_SEEK clamps to valid range (high)", () => {
    const frames = [makeTrailPoint(0), makeTrailPoint(1), makeTrailPoint(2)];
    let state = fleetReducer(initialState, {
      type: "REPLAY_LOADED",
      payload: { agentId: "agent-1", frames },
    });
    state = fleetReducer(state, { type: "REPLAY_SEEK", payload: 100 });
    expect(state.replay.currentIndex).toBe(2);
  });

  // ── COMMAND lifecycle ─────────────────────────────────────────────────────

  it("COMMAND_PENDING adds a record with PENDING status", () => {
    const state = fleetReducer(initialState, {
      type: "COMMAND_PENDING",
      payload: { tempId: "tmp-1", agent_id: "agent-1", command_type: "LAND" },
    });
    expect(state.commands).toHaveLength(1);
    expect(state.commands[0]).toMatchObject({
      id: "tmp-1",
      agent_id: "agent-1",
      command_type: "LAND",
      status: "PENDING",
    });
  });

  it("COMMAND_SENT_RECEIVED promotes oldest PENDING to SENT", () => {
    let state = fleetReducer(initialState, {
      type: "COMMAND_PENDING",
      payload: { tempId: "tmp-1", agent_id: "agent-1", command_type: "RTH" },
    });
    state = fleetReducer(state, {
      type: "COMMAND_SENT_RECEIVED",
      payload: { agent_id: "agent-1", command_id: "server-cmd-1", issued_at: "2024-01-01T00:00:00Z" },
    });
    expect(state.commands[0]).toMatchObject({
      id: "server-cmd-1",
      status: "SENT",
      issued_at: "2024-01-01T00:00:00Z",
    });
  });

  it("COMMAND_ERROR_RECEIVED marks oldest PENDING as FAILED", () => {
    let state = fleetReducer(initialState, {
      type: "COMMAND_PENDING",
      payload: { tempId: "tmp-2", agent_id: "agent-1", command_type: "CUT_MOTORS" },
    });
    state = fleetReducer(state, {
      type: "COMMAND_ERROR_RECEIVED",
      payload: { agent_id: "agent-1", error: "gateway offline" },
    });
    expect(state.commands[0]).toMatchObject({
      status: "FAILED",
      error: "gateway offline",
    });
  });

  it("COMMAND_ERROR_RECEIVED does nothing if no PENDING exists", () => {
    const state = fleetReducer(initialState, {
      type: "COMMAND_ERROR_RECEIVED",
      payload: { agent_id: "agent-1", error: "oops" },
    });
    expect(state.commands).toHaveLength(0);
  });

  // ── TOAST_PUSH / TOAST_DISMISS ────────────────────────────────────────────

  it("TOAST_PUSH adds a toast", () => {
    const state = fleetReducer(initialState, {
      type: "TOAST_PUSH",
      payload: { id: "t1", kind: "success", message: "Done" },
    });
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].message).toBe("Done");
  });

  it("TOAST_PUSH caps at 5 toasts", () => {
    let state = initialState;
    for (let i = 0; i < 7; i++) {
      state = fleetReducer(state, {
        type: "TOAST_PUSH",
        payload: { id: `t${i}`, kind: "info", message: `msg ${i}` },
      });
    }
    expect(state.toasts).toHaveLength(5);
    // Oldest are evicted (slice(-5) keeps last 5)
    expect(state.toasts[0].id).toBe("t2");
  });

  it("TOAST_DISMISS removes by id", () => {
    let state = fleetReducer(initialState, {
      type: "TOAST_PUSH",
      payload: { id: "t1", kind: "success", message: "Hello" },
    });
    state = fleetReducer(state, { type: "TOAST_DISMISS", payload: "t1" });
    expect(state.toasts).toHaveLength(0);
  });

  it("TOAST_DISMISS ignores unknown id", () => {
    let state = fleetReducer(initialState, {
      type: "TOAST_PUSH",
      payload: { id: "t1", kind: "success", message: "Hello" },
    });
    state = fleetReducer(state, { type: "TOAST_DISMISS", payload: "unknown" });
    expect(state.toasts).toHaveLength(1);
  });
});
