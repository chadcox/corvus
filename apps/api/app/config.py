from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://corvus:corvus@localhost:5432/corvus"
    )
    search_backend: str = "postgres"
    opensearch_url: str = "http://localhost:9200"
    opensearch_index_prefix: str = "ff"
    redis_url: str = "redis://localhost:6379/0"
    evidence_root: str = "/data/evidence"
    cors_origins: str = "http://localhost:5173"
    sigma_rules_root: str = "/opt/sigma/rules"
    sigma_ref: str = "master"
    sigma_refresh_interval_hours: float = 24.0
    chainsaw_bin: str = "/usr/local/bin/chainsaw"
    chainsaw_rules_root: str = "/opt/chainsaw/rules"
    chainsaw_mappings_root: str = "/opt/chainsaw/mappings"
    chainsaw_ref: str = "master"
    chainsaw_include_sigma: bool = True
    samples_root: str = "/samples"
    enable_validation_api: bool = False
    enable_admin_api: bool = False
    api_version: str = "0.1.0"
    upload_max_bytes: int = 10 * 1024 * 1024 * 1024
    extracted_max_files: int = 250_000
    extracted_max_bytes: int = 500 * 1024 * 1024 * 1024
    delete_evidence_after_ingest: bool = False
    auth_secret_key: str = "change-me-dev-auth-secret"
    auth_jwt_algorithm: str = "HS256"
    auth_token_exp_minutes: int = 480
    auth_trusted_proxies: str = ""
    auth_revocation_prefix: str = "auth:revoke"
    auth_revocation_fail_closed: bool = False
    auth_bootstrap_admin_username: str = ""
    auth_bootstrap_admin_password: str = ""
    admin_disk_usage_cache_seconds: int = 30
    docker_compose_project: str = "corvus"
    environment: str = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_trusted_proxy_list(self) -> list[str]:
        return [p.strip() for p in self.auth_trusted_proxies.split(",") if p.strip()]


DEFAULT_AUTH_SECRET = "change-me-dev-auth-secret"


def validate_security_settings(cfg: Settings) -> None:
    env = (cfg.environment or "development").strip().lower()
    if env in {"prod", "production", "staging"}:
        if cfg.auth_secret_key == DEFAULT_AUTH_SECRET:
            raise RuntimeError(
                "AUTH_SECRET_KEY is using the default value in a non-development environment"
            )
        if len(cfg.auth_secret_key) < 32:
            raise RuntimeError(
                "AUTH_SECRET_KEY must be at least 32 characters in a non-development environment"
            )


settings = Settings()
