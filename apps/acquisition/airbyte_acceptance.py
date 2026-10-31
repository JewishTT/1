"""Portable Airbyte acceptance configuration helpers.

The live proof derives its source config from the connector's SPEC and its selected
stream from DISCOVER. This keeps the acceptance test aligned with the exact pinned
connector image instead of shipping a hand-written stale catalog.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from shutil import copyfile
from typing import Any


def _enum_or_preferred(schema: dict[str, Any], preferred: tuple[str, ...]) -> str | None:
    """Choose a declared connector option; never invent an enum outside the SPEC."""
    choices = schema.get("enum") or []
    if not choices:
        constant = schema.get("const")
        return str(constant) if constant is not None else (
            str(schema["default"]) if schema.get("default") is not None else None
        )
    normalized = {str(value).lower(): str(value) for value in choices}
    for value in preferred:
        if value.lower() in normalized:
            return normalized[value.lower()]
    return str(choices[0])


def _object_choice(
    schema: dict[str, Any],
    preferred: dict[str, tuple[str, ...]],
) -> dict[str, Any] | None:
    properties = schema.get("properties") or {}
    chosen: dict[str, Any] = {}
    for name, child in properties.items():
        if child.get("type") == "object":
            nested = _object_choice(child, preferred)
            if nested is not None:
                chosen[name] = nested
            continue
        value = _enum_or_preferred(child, preferred.get(name, ()))
        if value is not None:
            chosen[name] = value
    if chosen:
        return chosen
    default = schema.get("default")
    return dict(default) if isinstance(default, dict) else None


def default_postgres_config(
    connector_spec: dict[str, Any],
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a local Postgres source config constrained by the connector SPEC."""
    env = environment if environment is not None else os.environ
    connection = connector_spec.get("connectionSpecification") or {}
    properties = connection.get("properties") or {}
    if not properties:
        raise ValueError("source-postgres SPEC has no connectionSpecification.properties")

    config: dict[str, Any] = {
        "host": env.get("COGNITIVE_AIRBYTE_PG_HOST", "host.docker.internal"),
        "port": int(env.get("COGNITIVE_AIRBYTE_PG_PORT", "5432")),
        "database": env.get("COGNITIVE_AIRBYTE_PG_DATABASE", "cognitive"),
        "username": env.get("COGNITIVE_AIRBYTE_PG_USERNAME", "cognitive"),
        "password": env.get("COGNITIVE_AIRBYTE_PG_PASSWORD", "cognitive"),
    }
    if "schemas" in properties:
        config["schemas"] = [
            item.strip()
            for item in env.get("COGNITIVE_AIRBYTE_PG_SCHEMAS", "public").split(",")
            if item.strip()
        ]

    preferences = {
        "mode": ("disable", "require", "prefer"),
        "tunnel_method": ("NO_TUNNEL",),
        "method": ("Standard", "standard", "Xmin", "xmin"),
    }
    for name in ("ssl_mode", "tunnel_method", "replication_method"):
        schema = properties.get(name)
        if schema and schema.get("type") == "object":
            selected = _object_choice(schema, preferences)
            if selected is not None:
                config[name] = selected

    required = set(connection.get("required") or [])
    missing = sorted(name for name in required if name not in config)
    if missing:
        raise ValueError(
            "source-postgres SPEC requires configuration fields not safely defaulted: "
            + ", ".join(missing)
            + "; provide COGNITIVE_AIRBYTE_CONFIG_FILE or COGNITIVE_AIRBYTE_CONFIG_JSON"
        )
    return config


def write_source_config(
    mount: Path,
    connector_spec: dict[str, Any],
    *,
    environment: dict[str, str] | None = None,
) -> Path:
    """Write one temporary source config; an explicit operator config takes precedence."""
    env = environment if environment is not None else os.environ
    mount.mkdir(parents=True, exist_ok=True)
    target = mount / "config.json"
    explicit_file = env.get("COGNITIVE_AIRBYTE_CONFIG_FILE", "").strip()
    explicit_json = env.get("COGNITIVE_AIRBYTE_CONFIG_JSON", "").strip()
    if explicit_file:
        copyfile(Path(explicit_file).expanduser(), target)
    elif explicit_json:
        target.write_text(json.dumps(json.loads(explicit_json), indent=2), encoding="utf-8")
    else:
        target.write_text(
            json.dumps(default_postgres_config(connector_spec, environment=env), indent=2),
            encoding="utf-8",
        )
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def write_configured_catalog(
    mount: Path,
    discovered_catalog: dict[str, Any],
    *,
    stream_name: str = "airbyte_smoke",
) -> tuple[Path, list[str]]:
    """Select exactly one discovered stream; fail closed when it is absent or unsupported."""
    mount.mkdir(parents=True, exist_ok=True)
    found: list[dict[str, Any]] = []
    for entry in discovered_catalog.get("streams", []):
        stream = entry.get("stream") if isinstance(entry, dict) else None
        stream = stream if isinstance(stream, dict) else entry
        if isinstance(stream, dict) and stream.get("name") == stream_name:
            found.append(stream)
    if not found:
        names = [
            (entry.get("stream") or entry).get("name")
            for entry in discovered_catalog.get("streams", [])
            if isinstance(entry, dict)
        ]
        raise ValueError(f"DISCOVER did not return {stream_name!r}; available streams: {names[:30]}")

    stream = found[0]
    supported = stream.get("supported_sync_modes") or ["full_refresh"]
    sync_mode = "full_refresh" if "full_refresh" in supported else (supported[0] if supported else None)
    if not sync_mode:
        raise ValueError(f"stream {stream_name!r} declares no supported sync mode")
    configured = {
        "streams": [{
            "stream": stream,
            "sync_mode": sync_mode,
            "destination_sync_mode": "append",
            "cursor_field": [],
            "primary_key": stream.get("source_defined_primary_key") or [],
            "selected": True,
        }]
    }
    target = mount / "catalog.json"
    target.write_text(json.dumps(configured, indent=2), encoding="utf-8")
    return target, [stream_name]


__all__ = ["default_postgres_config", "write_configured_catalog", "write_source_config"]
