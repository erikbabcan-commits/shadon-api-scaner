from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://straz:straz@postgres:5432/straz"
    redis_url: str = "redis://redis:6379/0"

    straz_admin_email: str = "admin@example.com"
    straz_admin_password: str = "change-me-now"
    straz_session_secret: str = "dev-secret-change-me-please-32chars"
    straz_cookie_secure: bool = False
    straz_cookie_name: str = "straz_session"
    straz_session_max_age: int = 60 * 60 * 24 * 14

    trusted_private_nets: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8"

    heartbeat_interval_minutes: int = 5
    nuclei_weekly_cron: str = "0 3 * * 1"

    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""

    heavy_scan_lock_key: str = "straz:lock:heavy_scan"
    heavy_scan_lock_ttl: int = 60 * 60

    @property
    def trusted_nets_list(self) -> list[str]:
        return [n.strip() for n in self.trusted_private_nets.split(",") if n.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
