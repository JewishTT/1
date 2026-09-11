"""Ontology pack registry (T003, FR-012, kafSIEM pattern).

Versioned schema packs declaring admissible entity types, properties and
relations. Packs are never overwritten — activating a change requires a NEW
version (reproducibility). Events and state carry refs, never blobs (I-5).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field

_MAX_INLINE_DESCRIPTOR_BYTES = 4096


class OntologyPackStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"


@dataclass
class OntologyPack:
    """Declared entity/property/relation space (FTM schema/ontology)."""

    pack_id: str = field(default_factory=lambda: "OP-" + uuid.uuid4().hex[:12])
    pack_version: str = "ontology-v1"
    entity_types: list[str] = field(
        default_factory=lambda: [
            "PERSON", "ORG", "LOCATION", "EMAIL", "PHONE", "DOMAIN",
            "USERNAME", "DOCUMENT", "URL", "IPV4", "CVE", "CRYPTO_ADDRESS",
        ]
    )
    properties: dict = field(default_factory=dict)
    relations: list[str] = field(
        default_factory=lambda: ["works_at", "owns", "controls", "corresponds_to", "linked_to"]
    )
    status: OntologyPackStatus = OntologyPackStatus.DRAFT
    tenant_id: str = "default-tenant"

    def allows_type(self, type_name: str) -> bool:
        return type_name.upper() in {t.upper() for t in self.entity_types}

    def allows_relation(self, relation: str) -> bool:
        return relation in self.relations

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "entity_types": self.entity_types,
            "properties": self.properties,
            "relations": self.relations,
            "status": self.status.value,
            "tenant_id": self.tenant_id,
        }


class OntologyPackRegistry:
    """Versioned registry: DRAFT -> REGISTERED -> ACTIVE; never overwrite a version."""

    def __init__(self, max_inline: int = 1024) -> None:
        self._max_inline = max_inline
        self._packs: dict[str, OntologyPack] = {}   # pack_version -> pack
        self._active: dict[str, str] = {}           # tenant_id -> pack_version

    def register(self, pack: OntologyPack) -> OntologyPack:
        descriptor = pack.to_dict()
        # I-5: packs carry refs/schema, never blobs (self-contained guard —
        # `domain` may be shadowed by the control-plane package in some test roots).
        import json

        blob = json.dumps(descriptor, sort_keys=True).encode("utf-8")
        if len(blob) > _MAX_INLINE_DESCRIPTOR_BYTES:
            raise ValueError(
                f"ontology pack descriptor too large inline ({len(blob)} bytes); "
                "carry refs, not blobs (I-5)"
            )
        if pack.pack_version in self._packs:
            raise ValueError(f"ontology pack version already registered: {pack.pack_version}")
        pack.status = OntologyPackStatus.REGISTERED
        self._packs[pack.pack_version] = pack
        return pack

    def activate(self, pack_version: str, tenant_id: str | None = None) -> OntologyPack:
        tenant = tenant_id or "default-tenant"
        pack = self._packs.get(pack_version)
        if pack is None:
            raise KeyError(pack_version)
        pack.status = OntologyPackStatus.ACTIVE
        self._active[tenant] = pack_version
        return pack

    def active_for(self, tenant_id: str | None = None) -> OntologyPack | None:
        tenant = tenant_id or "default-tenant"
        version = self._active.get(tenant)
        return self._packs.get(version) if version else None

    def versions(self) -> list[str]:
        return sorted(self._packs)