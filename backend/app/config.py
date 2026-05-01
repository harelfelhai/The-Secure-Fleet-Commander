from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://fleet:fleet@localhost:5432/fleet_commander"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    heartbeat_timeout_seconds: int = 10
    zones_config_path: str = "../shared/schemas/zones.json"

    debug: bool = False


settings = Settings()
