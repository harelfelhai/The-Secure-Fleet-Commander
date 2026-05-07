from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    backend_ws_url: str = "ws://localhost:8000"
    backend_api_url: str = "http://localhost:8000"
    hardware_id: str = "sim-drone-001"

    # Telemetry rate
    telemetry_hz: float = 5.0

    # Flight path — circular orbit
    center_lat: float = 32.0853  # Tel Aviv area
    center_lon: float = 34.7818
    orbit_radius_deg: float = 0.005  # ≈ 500 m
    orbit_period_seconds: float = 30.0  # one full orbit

    # Drone state
    initial_altitude_m: float = 50.0
    battery_drain_pct_per_sec: float = 0.5  # 100% → LOW_BATTERY in ~2.7 min

    # Offline buffer
    offline_buffer_path: str = "offline_buffer.db"
    offline_buffer_max_size: int = 1000

    # Reconnection
    reconnect_backoff_max_seconds: float = 30.0


settings = SimulatorSettings()
