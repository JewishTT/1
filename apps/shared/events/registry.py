"""Schema Registry client + versioned payload registry (T009, FR-023, R-7).

Payloads are registered by ``(event_type, event_version)`` against the Schema
Registry (Redpanda-compatible protocol). The registry validates that only
registered payloads are produced/consumed; unknown versions are rejected for
production and surfaced as errors for consumption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from config.settings import get_settings


@dataclass(frozen=True)
class PayloadRegistration:
    event_type: str
    event_version: str
    descriptor: dict  # schema bytes / json schema / proto descriptor ref


class PayloadNotRegisteredError(KeyError):
    pass


class SchemaRegistryClient:
    """Registry-validated event payload manifest with lazy Schema Registry sync."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or get_settings().kafka.schema_registry_url).rstrip("/")
        self._manifest: dict[str, PayloadRegistration] = {}
        self._client: httpx.AsyncClient | None = None
        self._synced_basename: set[str] = set()

    def register(self, registration: PayloadRegistration) -> None:
        """Register a payload version locally (application manifest)."""
        self._manifest[(registration.event_type, registration.event_version)] = registration

    def lookup(self, event_type: str, event_version: str) -> PayloadRegistration:
        try:
            return self._manifest[(event_type, event_version)]
        except KeyError as exc:
            raise PayloadNotRegisteredError(event_type, event_version) from exc

    def versions(self, event_type: str) -> list[str]:
        return sorted(v for (et, v) in self._manifest if et == event_type)

    async def ensure_synced(self, force: bool = False) -> None:
        """Sync registered payloads to Schema Registry and fetch peer subjects."""
        if not self._manifest:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            for (event_type, event_version), reg in list(self._manifest.items()):
                subject = f"{event_type}-value"
                if subject in self._synced_basename and not force:
                    continue
                current = await client.get(
                    f"{self.base_url}/subjects/{subject}/versions/latest",
                )
                expected = self._encode_payload(reg)
                if current.status_code == 404:
                    await self._register_subject(client, subject, expected)
                elif current.status_code == 200 and current.json().get("schema") != expected:
                    await self._register_subject(client, subject, expected)
                self._synced_basename.add(subject)

    async def fetch_schema(self, event_type: str, event_version: str) -> str | None:
        subject = f"{event_type}-value"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/subjects/{subject}/versions/{event_version}",
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("schema")

    @staticmethod
    def _encode_payload(reg: PayloadRegistration) -> str:
        return json.dumps(reg.descriptor, sort_keys=True)

    @staticmethod
    async def _register_subject(client: httpx.AsyncClient, subject: str, schema: str) -> None:
        await client.post(
            f"{client.base_url}/subjects/{subject}/versions",
            json={"schema": schema},
            timeout=10,
        )


_default_registry: SchemaRegistryClient | None = None


def get_registry() -> SchemaRegistryClient:
    global _default_registry
    if _default_registry is None:
        _default_registry = SchemaRegistryClient()
    return _default_registry