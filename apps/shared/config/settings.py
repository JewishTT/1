"""Environment bootstrap for all Python apps (T007).

Reads ``.env`` from repo root; per-app overrides are applied by passing a
nested section via ``COGNITIVE_APP_<name>`` env vars or by subclassing
`Settings` with ``model_config["env_prefix"]``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[4]


class StorageSettings(BaseSettings):
    endpoint: str = "http://localhost:9000"
    access_key: str = "demo"
    secret_key: str = "demopass"
    raw_bucket: str = "knowledge"

    model_config = SettingsConfigDict(env_prefix="S3_", case_sensitive=False)


class KafkaSettings(BaseSettings):
    bootstrap_servers: str = "localhost:9092"
    schema_registry_url: str = "http://localhost:8081"

    model_config = SettingsConfigDict(env_prefix="KAFKA_", case_sensitive=False)


class PostgresSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    database: str = "cognitive"
    user: str = "cognitive"
    password: str = "cognitive"

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", case_sensitive=False)

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Settings(BaseSettings):
    env: str = Field(default="dev", alias="COGNITIVE_ENV")

    storage: StorageSettings = StorageSettings()
    kafka: KafkaSettings = KafkaSettings()
    postgres: PostgresSettings = PostgresSettings()

    redis_url: str = "redis://localhost:6379/0"
    opensearch_url: str = "http://localhost:9200"
    clickhouse_url: str = "http://localhost:8123"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "cognitive"
    temporal_host: str = "localhost:7233"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings; overridable in tests via dependency override."""
    return Settings()


def settings_for_app(app_name: str) -> Settings:
    """Per-app settings: same base but honours a ``COGNITIVE_APP_<NAME>_*`` override set."""
    prefix = f"COGNITIVE_APP_{app_name.upper()}_"
    return Settings(_env_prefix=prefix) if prefix else get_settings()