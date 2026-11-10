"""Optional FollowTheMoney interchange with a separate provenance sidecar.

FollowTheMoney is an MIT-licensed entity model. Cognitive retains ownership of
its canonical identity and claim lifecycle; this module only exports/imports a
curated interoperability shape. It never merges identities or admits claims.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence


SCHEMAS = frozenset({"Person", "Company", "Organization", "Payment", "Asset"})
SAFE_PROPERTIES: dict[str, frozenset[str]] = {
    "Person": frozenset({"name", "position", "website"}),
    "Company": frozenset({"name", "registrationNumber", "jurisdiction", "incorporationDate", "website"}),
    "Organization": frozenset({"name", "website", "jurisdiction"}),
    "Payment": frozenset({"payer", "beneficiary", "amount", "currency", "date", "description"}),
    "Asset": frozenset({"name", "assetType", "currency", "amount", "website"}),
}
MAX_VALUES_PER_PROPERTY = 20
MAX_VALUE_LENGTH = 2_000


class FtMExportError(ValueError):
    """The internal entity cannot be represented safely as an FtM entity."""


@dataclass(frozen=True)
class FtMExport:
    record: dict[str, Any]
    provenance: dict[str, Any]


def stable_ftm_id(tenant_id: str, entity_id: str) -> str:
    if not tenant_id.strip() or not entity_id.strip():
        raise ValueError("tenant_id and entity_id are required")
    material = f"{tenant_id.strip()}\x00{entity_id.strip()}".encode("utf-8")
    return "cog-" + hashlib.sha256(material).hexdigest()[:32]


def _values(properties: Mapping[str, Any], schema: str) -> dict[str, list[str]]:
    allowed = SAFE_PROPERTIES[schema]
    result: dict[str, list[str]] = {}
    for key, raw in properties.items():
        if key not in allowed:
            continue
        candidates = raw if isinstance(raw, (list, tuple, set)) else [raw]
        normalized: list[str] = []
        for value in candidates:
            if value is None or isinstance(value, bool):
                continue
            rendered = str(value).strip()
            if not rendered or len(rendered) > MAX_VALUE_LENGTH:
                continue
            if rendered not in normalized:
                normalized.append(rendered)
            if len(normalized) >= MAX_VALUES_PER_PROPERTY:
                break
        if normalized:
            result[key] = normalized
    return result


def build_ftm_export(
    *,
    tenant_id: str,
    entity_id: str,
    schema: str,
    properties: Mapping[str, Any],
    dataset_id: str,
    source_ids: Sequence[str] = (),
    observation_refs: Sequence[str] = (),
    claim_refs: Sequence[str] = (),
) -> FtMExport:
    if schema not in SCHEMAS:
        raise FtMExportError(f"schema is not in the supported interchange allowlist: {schema}")
    if not dataset_id.strip():
        raise FtMExportError("dataset_id is required")
    safe_properties = _values(properties, schema)
    if not safe_properties.get("name") and schema in {"Person", "Company", "Organization", "Asset"}:
        raise FtMExportError(f"{schema} export requires a source-grounded name")
    record = {
        "id": stable_ftm_id(tenant_id, entity_id),
        "schema": schema,
        "properties": safe_properties,
        "datasets": [dataset_id.strip()],
    }
    provenance = {
        "ftm_id": record["id"],
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "source_ids": sorted({str(item) for item in source_ids if str(item).strip()}),
        "observation_refs": sorted({str(item) for item in observation_refs if str(item).strip()}),
        "claim_refs": sorted({str(item) for item in claim_refs if str(item).strip()}),
        "exported_at": datetime.now(UTC).isoformat(),
        "identity_merge_performed": False,
        "claim_admission_performed": False,
    }
    return FtMExport(record=record, provenance=provenance)


def validate_with_followthemoney(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate against the installed FtM model; import remains optional at runtime."""
    try:
        from followthemoney import model
    except ImportError as exc:
        raise FtMExportError(
            "optional dependency followthemoney is not installed; install the documented adapter extra"
        ) from exc
    try:
        proxy = model.get_proxy(copy.deepcopy(dict(record)), cleaned=False)
        return proxy.to_dict()
    except Exception as exc:  # noqa: BLE001 - normalize third-party model validation errors
        raise FtMExportError(f"FollowTheMoney rejected the interchange record: {type(exc).__name__}") from exc


def jsonl_lines(exports: Sequence[FtMExport]) -> tuple[str, str]:
    """Return entity JSONL and a separate provenance JSONL; never mix sidecar into FtM."""
    import json

    entities = "\n".join(
        json.dumps(item.record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for item in exports
    )
    provenance = "\n".join(
        json.dumps(item.provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for item in exports
    )
    return (entities + ("\n" if entities else ""), provenance + ("\n" if provenance else ""))
