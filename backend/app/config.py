from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_commander"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    heartbeat_timeout_seconds: int = 10
    watchdog_timeout_seconds: int = 20  # 2x heartbeat — close if no frames received
    zones_config_path: str = "../shared/schemas/zones.json"

    battery_warn_pct: float = 20.0  # alert fires when battery drops below this
    battery_clear_pct: float = 25.0  # hysteresis — alert clears when battery rises above this

    # Breadcrumb persistence throttle — write to DB at most once per interval,
    # unless a rule fires (alerts always trigger a persist regardless of interval).
    persist_interval_seconds: float = 2.0

    debug: bool = False


settings = Settings()
