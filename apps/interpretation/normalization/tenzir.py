"""Tenzir-backed structural normalization for already-parsed observation records.

Tenzir is an optional external dataflow engine, not an authority for raw evidence,
identity, claims, or graph state. The Python payload parser remains the only producer
of exact source byte spans and deferred occurrence addresses. This adapter sends a
bounded batch of those records to a Tenzir Node, adds derived structural columns, and
refuses any output that changes or drops source-observation fields.

The adapter uses the documented Tenzir Node REST API:
  POST /pipeline/launch  -> hidden, bounded-lifetime interactive pipeline
  POST /serve            -> drain its output stream

Only this module owns the TQL transform. Case/user input is rendered as typed TQL
literals; callers cannot submit arbitrary TQL through the research-case API.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

NORMALIZATION_SCHEMA = "cognitive.observed-field-normalization/v1"
NORMALIZATION_ENGINE = "tenzir-node"
TENZIR_API_PREFIX = "/api/v0"
NORMALIZATION_VERSION = "tenzir-observed-fields-v1"

# Keep this transformation intentionally additive. Never use ocsf_cast / ocsf_trim
# on open-world evidence records: those operators can remove fields outside a target
# schema, while the platform contract requires every unexpected source field to remain
# reachable. Original field, value, value_type, byte_span, address and refusal fields
# are checked after the Tenzir run and cannot be overwritten.
_TQL_TRANSFORM = (
    "normalized_field_path = field.to_lower()\n"
    "normalized_value_type = value_type.to_lower()\n"
    "value_length_chars = value.length_chars()\n"
    "value_length_bytes = value.length_bytes()\n"
    'value_is_numeric_lexeme = value.match_regex("^[+-]?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$")\n'
    "has_nonempty_surface = value.trim() != \"\"\n"
    "byte_span_width = byte_span.get(1) - byte_span.get(0) if byte_span != null else null\n"
    "structural_role = \"container\" if value_type == \"nested\" else \"null\" if value_type == \"null\" else \"surface\""
)
_PIPELINE_DIGEST = "sha256:" + hashlib.sha256(
    (NORMALIZATION_VERSION + "\n" + _TQL_TRANSFORM).encode("utf-8")
).hexdigest()

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENABLED_VALUES = {"1", "true", "yes", "on"}
_PROTECTED_FIELDS = (
    "field",
    "value",
    "value_type",
    "byte_span",
    "depth",
    "label",
    "address",
    "address_refusal",
)


class TenzirError(RuntimeError):
    """A Tenzir adapter/configuration/output-contract failure with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail[:600]


@dataclass(frozen=True)
class TenzirSettings:
    node_url: str
    token: str = ""
    timeout_seconds: float = 45.0
    max_batch_records: int = 256
    max_request_bytes: int = 2_000_000
    max_response_bytes: int = 4_000_000
    max_output_records: int = 4096
    engine_version: str = "unknown"
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        parsed = urlsplit(self.node_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise TenzirError("tenzir_config_invalid", "TENZIR_NODE_URL must be an absolute http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise TenzirError(
                "tenzir_config_invalid",
                "TENZIR_NODE_URL must not embed credentials, query parameters or a fragment",
            )
        if parsed.path not in {"", "/"}:
            raise TenzirError("tenzir_config_invalid", "TENZIR_NODE_URL must be the node origin, without an API path")
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        host_is_loopback = (parsed.hostname or "").lower() in local_hosts
        if parsed.scheme == "http" and not host_is_loopback and not self.allow_insecure_http:
            raise TenzirError(
                "tenzir_insecure_transport",
                "non-loopback Tenzir HTTP requires TENZIR_ALLOW_INSECURE_HTTP=true; use HTTPS in production",
            )
        if (parsed.scheme == "https" or not host_is_loopback) and not self.token.strip():
            raise TenzirError(
                "tenzir_token_missing",
                "HTTPS and non-loopback Tenzir endpoints require TENZIR_NODE_TOKEN",
            )
        if self.timeout_seconds <= 0 or not math.isfinite(self.timeout_seconds):
            raise TenzirError("tenzir_config_invalid", "TENZIR_TIMEOUT_SECONDS must be positive and finite")
        if self.max_batch_records < 1 or self.max_batch_records > 4096:
            raise TenzirError("tenzir_config_invalid", "TENZIR_MAX_BATCH_RECORDS must be in [1, 4096]")
        if self.max_request_bytes < 1024:
            raise TenzirError("tenzir_config_invalid", "TENZIR_MAX_REQUEST_BYTES must be at least 1024")
        if self.max_response_bytes < 1024:
            raise TenzirError("tenzir_config_invalid", "TENZIR_MAX_RESPONSE_BYTES must be at least 1024")
        if self.max_output_records < 1 or self.max_output_records > 100_000:
            raise TenzirError("tenzir_config_invalid", "TENZIR_MAX_OUTPUT_RECORDS must be in [1, 100000]")

    @classmethod
    def from_env(cls) -> "TenzirSettings | None":
        if os.getenv("TENZIR_ENABLED", "false").strip().lower() not in _ENABLED_VALUES:
            return None
        endpoint = os.getenv("TENZIR_NODE_URL", "").strip()
        if not endpoint:
            raise TenzirError(
                "tenzir_config_missing",
                "TENZIR_ENABLED is true but TENZIR_NODE_URL is empty",
            )
        try:
            return cls(
                node_url=endpoint.rstrip("/"),
                token=os.getenv("TENZIR_NODE_TOKEN", ""),
                timeout_seconds=float(os.getenv("TENZIR_TIMEOUT_SECONDS", "45")),
                max_batch_records=int(os.getenv("TENZIR_MAX_BATCH_RECORDS", "256")),
                max_request_bytes=int(os.getenv("TENZIR_MAX_REQUEST_BYTES", "2000000")),
                max_response_bytes=int(os.getenv("TENZIR_MAX_RESPONSE_BYTES", "4000000")),
                max_output_records=int(os.getenv("TENZIR_MAX_OUTPUT_RECORDS", "4096")),
                engine_version=os.getenv("TENZIR_NODE_VERSION", "unknown").strip() or "unknown",
                allow_insecure_http=(
                    os.getenv("TENZIR_ALLOW_INSECURE_HTTP", "false").strip().lower()
                    in _ENABLED_VALUES
                ),
            )
        except ValueError as exc:
            raise TenzirError("tenzir_config_invalid", f"invalid numeric Tenzir setting: {exc}") from exc


@dataclass(frozen=True)
class TenzirNormalization:
    records: list[dict[str, Any]]
    pipeline_digest: str
    engine: str = NORMALIZATION_ENGINE
    engine_version: str = "unknown"
    schema: str = NORMALIZATION_SCHEMA

    @property
    def record_count(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "pipeline_version": NORMALIZATION_VERSION,
            "pipeline_digest": self.pipeline_digest,
            "record_count": self.record_count,
            "records": self.records,
        }


def _tql_literal(value: Any) -> str:
    """Render JSON-compatible values as TQL literals without string interpolation."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TenzirError("tenzir_input_invalid", "non-finite numbers are not valid evidence fields")
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_tql_literal(item) for item in value) + "]"
    if isinstance(value, Mapping):
        entries = []
        for key in sorted(value):
            name = str(key)
            if not _IDENTIFIER.fullmatch(name):
                raise TenzirError(
                    "tenzir_input_invalid",
                    f"field name {name!r} cannot be represented as a TQL record identifier",
                )
            entries.append(f"{name}: {_tql_literal(value[key])}")
        return "{" + ", ".join(entries) + "}"
    raise TenzirError(
        "tenzir_input_invalid",
        f"unsupported structured record value type {type(value).__name__}",
    )


def _normalization_definition(records: Sequence[Mapping[str, Any]], *, first_ordinal: int = 0) -> str:
    events = []
    for local_ordinal, row in enumerate(records):
        event = {name: row.get(name) for name in _PROTECTED_FIELDS}
        event["_platform_ordinal"] = first_ordinal + local_ordinal
        events.append(_tql_literal(event))
    return "from " + ", ".join(events) + " | " + _TQL_TRANSFORM.replace("\n", " | ")


class TenzirNodeNormalizer:
    """Run the reviewed additive TQL transform on the configured Tenzir Node."""

    def __init__(self, settings: TenzirSettings) -> None:
        self.settings = settings

    @classmethod
    def from_env(cls) -> "TenzirNodeNormalizer | None":
        settings = TenzirSettings.from_env()
        return cls(settings) if settings is not None else None

    async def normalize_records(
        self, records: Sequence[Mapping[str, Any]]
    ) -> TenzirNormalization:
        """Return an enriched copy; the original parser records are never mutated."""
        if not records:
            return TenzirNormalization(
                records=[],
                pipeline_digest=_PIPELINE_DIGEST,
                engine_version=self.settings.engine_version,
            )
        if len(records) > self.settings.max_output_records:
            raise TenzirError(
                "tenzir_input_limit",
                f"{len(records)} records exceed TENZIR_MAX_OUTPUT_RECORDS={self.settings.max_output_records}",
            )

        normalized: list[dict[str, Any] | None] = [None] * len(records)
        offset = 0
        # The input records are escaped once into TQL literals and again into the
        # JSON REST body. Budget conservatively for both encodings and pipeline syntax
        # so a nominally bounded batch is not rejected only after compilation.
        fixed_overhead = 2 * len(_TQL_TRANSFORM.encode("utf-8")) + 512
        while offset < len(records):
            chunk: list[Mapping[str, Any]] = []
            chunk_bytes = fixed_overhead
            while offset + len(chunk) < len(records) and len(chunk) < self.settings.max_batch_records:
                candidate = records[offset + len(chunk)]
                event = {name: candidate.get(name) for name in _PROTECTED_FIELDS}
                event["_platform_ordinal"] = offset + len(chunk)
                rendered = _tql_literal(event)
                candidate_bytes = 2 * len(rendered.encode("utf-8")) + 8
                if candidate_bytes + fixed_overhead > self.settings.max_request_bytes:
                    raise TenzirError(
                        "tenzir_input_limit",
                        f"record {offset + len(chunk)} alone exceeds TENZIR_MAX_REQUEST_BYTES",
                    )
                if chunk and chunk_bytes + candidate_bytes > self.settings.max_request_bytes:
                    break
                chunk.append(candidate)
                chunk_bytes += candidate_bytes
            if not chunk:
                raise TenzirError("tenzir_input_limit", "could not form a bounded Tenzir batch")
            outputs = await self._run_chunk(chunk, first_ordinal=offset)
            for ordinal, row in outputs:
                if ordinal < offset or ordinal >= offset + len(chunk):
                    raise TenzirError("tenzir_output_invalid", "output ordinal is outside the submitted batch")
                if normalized[ordinal] is not None:
                    raise TenzirError("tenzir_output_duplicate", f"Tenzir returned ordinal {ordinal} twice")
                normalized[ordinal] = row
            offset += len(chunk)

        if any(row is None for row in normalized):
            missing = [i for i, row in enumerate(normalized) if row is None]
            raise TenzirError(
                "tenzir_output_incomplete",
                f"Tenzir dropped {len(missing)} record(s); first missing ordinal {missing[0]}",
            )
        return TenzirNormalization(
            records=[row for row in normalized if row is not None],
            pipeline_digest=_PIPELINE_DIGEST,
            engine_version=self.settings.engine_version,
        )

    async def _run_chunk(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        first_ordinal: int,
    ) -> list[tuple[int, dict[str, Any]]]:
        definition = _normalization_definition(records, first_ordinal=first_ordinal)
        definition_size = len(definition.encode("utf-8"))
        if definition_size > self.settings.max_request_bytes:
            raise TenzirError(
                "tenzir_input_limit",
                f"compiled TQL definition is {definition_size} bytes; limit is {self.settings.max_request_bytes}",
            )

        serve_id = "cognitive-observed-" + secrets.token_hex(12)
        launch = await asyncio.to_thread(
            self._post_json,
            "/pipeline/launch",
            {
                "definition": definition,
                "name": NORMALIZATION_VERSION,
                "hidden": True,
                "ttl": "2m",
                "serve_id": serve_id,
                "serve_buffer_size": max(16, min(len(records) + 1, self.settings.max_batch_records + 1)),
                "autodelete": {
                    "completed": True,
                    "failed": True,
                    "stopped": True,
                },
            },
        )
        if launch.get("error"):
            raise TenzirError("tenzir_pipeline_rejected", str(launch["error"]))
        pipeline_id = str(launch.get("id") or "")
        if not pipeline_id:
            raise TenzirError(
                "tenzir_pipeline_rejected",
                "Tenzir did not create an interactive pipeline output stream",
            )

        deadline = time.monotonic() + self.settings.timeout_seconds
        continuation: str | None = None
        rows: list[tuple[int, dict[str, Any]]] = []
        try:
            while True:
                if time.monotonic() >= deadline:
                    raise TenzirError("tenzir_timeout", "Tenzir output stream exceeded its deadline")
                request: dict[str, Any] = {
                    "serve_id": serve_id,
                    "max_events": self.settings.max_batch_records,
                    "min_events": 1,
                    "timeout": "2s",
                    "schema": "never",
                }
                if continuation:
                    request["continuation_token"] = continuation
                result = await asyncio.to_thread(self._post_json, "/serve", request)
                state = str(result.get("state") or "")
                events = result.get("events")
                if not isinstance(events, list):
                    raise TenzirError("tenzir_output_invalid", "Tenzir /serve response has no events array")
                for event in events:
                    if not isinstance(event, Mapping):
                        raise TenzirError("tenzir_output_invalid", "Tenzir emitted a non-record event")
                    data = event.get("data", event)
                    if not isinstance(data, Mapping):
                        raise TenzirError("tenzir_output_invalid", "Tenzir event data is not a record")
                    try:
                        ordinal = int(data["_platform_ordinal"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise TenzirError(
                            "tenzir_output_invalid",
                            "Tenzir output is missing the protected _platform_ordinal",
                        ) from exc
                    original_local = ordinal - first_ordinal
                    if original_local < 0 or original_local >= len(records):
                        raise TenzirError("tenzir_output_invalid", "Tenzir returned an invalid record ordinal")
                    original = dict(records[original_local])
                    for field in _PROTECTED_FIELDS:
                        if field not in data or data[field] != original.get(field):
                            raise TenzirError(
                                "tenzir_mutated_evidence",
                                f"Tenzir changed or dropped protected source field {field!r} at ordinal {ordinal}",
                            )
                    normalized_path = data.get("normalized_field_path")
                    normalized_type = data.get("normalized_value_type")
                    derived = {
                        "field_path": normalized_path,
                        "value_type": normalized_type,
                        "value_length_chars": data.get("value_length_chars"),
                        "value_length_bytes": data.get("value_length_bytes"),
                        "value_is_numeric_lexeme": data.get("value_is_numeric_lexeme"),
                        "has_nonempty_surface": data.get("has_nonempty_surface"),
                        "byte_span_width": data.get("byte_span_width"),
                        "structural_role": data.get("structural_role"),
                    }
                    if (
                        not isinstance(normalized_path, str)
                        or not isinstance(normalized_type, str)
                        or not isinstance(derived["value_length_chars"], int)
                        or not isinstance(derived["value_length_bytes"], int)
                        or not isinstance(derived["value_is_numeric_lexeme"], bool)
                        or not isinstance(derived["has_nonempty_surface"], bool)
                        or (
                            derived["byte_span_width"] is not None
                            and not isinstance(derived["byte_span_width"], int)
                        )
                        or derived["structural_role"] not in {"container", "null", "surface"}
                    ):
                        raise TenzirError(
                            "tenzir_output_invalid",
                            f"Tenzir omitted or mistyped derived structural columns at ordinal {ordinal}",
                        )
                    span = original.get("byte_span")
                    expected_width = (
                        int(span[1]) - int(span[0])
                        if isinstance(span, list) and len(span) == 2
                        else None
                    )
                    if derived["byte_span_width"] != expected_width:
                        raise TenzirError(
                            "tenzir_output_invalid",
                            f"Tenzir computed an inconsistent byte span width at ordinal {ordinal}",
                        )
                    rows.append((
                        ordinal,
                        {
                            "ordinal": ordinal,
                            "record": original,
                            "normalized": derived,
                        },
                    ))
                    if len(rows) > len(records):
                        raise TenzirError("tenzir_output_duplicate", "Tenzir emitted more records than submitted")
                continuation_value = result.get("next_continuation_token")
                continuation = str(continuation_value) if continuation_value else None
                if state == "failed":
                    raise TenzirError("tenzir_pipeline_failed", "Tenzir reported a failed pipeline state")
                if state == "completed" and continuation is None:
                    break
                if state not in {"running", "completed"}:
                    raise TenzirError("tenzir_output_invalid", f"unknown Tenzir pipeline state {state!r}")
                if continuation is None and not events:
                    raise TenzirError(
                        "tenzir_output_invalid",
                        "Tenzir output stream became terminal without a completed state",
                    )
        except Exception:
            # Hidden pipelines have a finite TTL. Explicit delete is best-effort;
            # it must not mask the original pipeline / data-contract failure.
            try:
                await asyncio.to_thread(self._post_json, "/pipeline/delete", {"id": pipeline_id})
            except Exception:
                pass
            raise

        if len(rows) != len(records):
            raise TenzirError(
                "tenzir_output_incomplete",
                f"Tenzir returned {len(rows)} record(s) for {len(records)} submitted",
            )
        ordinals = [ordinal for ordinal, _ in rows]
        if len(set(ordinals)) != len(ordinals):
            raise TenzirError("tenzir_output_duplicate", "Tenzir returned a duplicate record ordinal")
        return rows

    def _post_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self.settings.max_request_bytes:
            raise TenzirError(
                "tenzir_input_limit",
                f"Tenzir REST request is {len(body)} bytes; limit is {self.settings.max_request_bytes}",
            )
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.token:
            headers["X-Tenzir-Token"] = self.settings.token
        request = Request(
            self.settings.node_url.rstrip("/") + TENZIR_API_PREFIX + "/" + path.lstrip("/"),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=min(self.settings.timeout_seconds, 15.0)) as response:
                raw = response.read(self.settings.max_response_bytes + 1)
        except HTTPError as exc:
            try:
                error_body = exc.read(min(self.settings.max_response_bytes, 4096)).decode("utf-8", "replace")
            except Exception:
                error_body = ""
            raise TenzirError(
                "tenzir_http_error",
                f"Tenzir endpoint {path} returned HTTP {exc.code}"
                + (f": {error_body[:300]}" if error_body else ""),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TenzirError(
                "tenzir_unreachable",
                f"Tenzir endpoint {path} is unreachable ({type(exc).__name__})",
            ) from exc
        if len(raw) > self.settings.max_response_bytes:
            raise TenzirError(
                "tenzir_response_limit",
                f"Tenzir endpoint {path} exceeded {self.settings.max_response_bytes} response bytes",
            )
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TenzirError("tenzir_response_invalid", f"Tenzir endpoint {path} returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise TenzirError("tenzir_response_invalid", f"Tenzir endpoint {path} returned a non-object JSON value")
        return decoded
