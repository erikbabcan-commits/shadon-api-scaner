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
    supply_chain_weekly_cron: str = "0 4 * * 1"

    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""

    heavy_scan_lock_key: str = "straz:lock:heavy_scan"
    heavy_scan_lock_ttl: int = 60 * 60

    internetdb_base_url: str = "https://internetdb.shodan.io"
    internetdb_cache_ttl: int = 60 * 60 * 24

    # Scoped port set for naabu (no full-range scans)
    naabu_ports: str = (
        "21,22,25,53,80,110,143,443,445,465,587,993,995,1433,1521,3306,3389,"
        "5432,5900,6379,8080,8443,9200,27017"
    )

    straz_env: str = "development"
    straz_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    straz_cookie_samesite: str = "lax"
    straz_cookie_domain: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.straz_cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.straz_env.lower() in ("prod", "production")

    @property
    def trusted_nets_list(self) -> list[str]:
        return [n.strip() for n in self.trusted_private_nets.split(",") if n.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
