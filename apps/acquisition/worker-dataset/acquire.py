"""Dataset acquisition worker (T094): parquet/bulk artifacts -> gate.

Reads a Parquet artifact (local file or HTTP URL) and stores the artifact bytes
content-addressed through the single Observation Gate, with schema metadata.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import pyarrow.parquet as pq


async def _fetch_bytes(source: str) -> tuple[bytes, dict]:
    parsed = urlsplit(source)
    if parsed.scheme in ("http", "https"):
        import httpx

        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.get(source)
            resp.raise_for_status()
            return resp.content, {"remote": source}
    if len(parsed.scheme) <= 1:  # bare path or windows drive (c:)
        path = source.removeprefix("local:").removeprefix("file:")
        return await asyncio.to_thread(_read_file, path), {}
    raise ValueError(f"unsupported dataset source scheme: {parsed.scheme!r}")


def _read_file(path: str) -> bytes:
    with open(path, "rb") as fh:  # noqa: ASYNC101 - inside to_thread
        return fh.read()


def parquet_meta(body: bytes, *, source: str) -> dict:
    meta: dict = {"schema": [], "row_groups": [], "format": "parquet"}
    try:
        if len(body) < 512 * 1024 * 1024:
            import io

            pf = pq.ParquetFile(io.BytesIO(body))
            meta["schema"] = [str(f.name) + ":" + str(f.type) for f in pf.schema_arrow]
            meta["row_groups"] = [rg.num_rows for rg in pf.metadata.row_groups]
            meta["rows"] = sum(meta["row_groups"])
    except Exception:  # pragma: no cover - non-parquet payload should still land raw
        pass
    return meta


async def acquire(task: dict) -> dict:
    gate = task.get("observation_gate")
    if gate is None:
        raise ValueError("task requires 'observation_gate' (Observation boundary)")
    source = task.get("dataset_url") or task.get("uri")
    if not source:
        raise ValueError("task requires 'dataset_url' (parquet/bulk source)")
    body, extra = await _fetch_bytes(source)
    obs = await gate.ingest(
        body=body,
        uri=source,
        tenant_id=task.get("tenant_id", "tenant-demo"),
        investigation_id=task.get("investigation_id"),
        source_id=task.get("source_id"),
        work_id=task.get("work_id"),
        region_id=task.get("region_id"),
        content_type="application/parquet",
        collector="dataset-worker",
        collector_version="2.0.0",
        source_kind="dataset",
    )
    obs["meta"] = {**extra, **parquet_meta(body, source=source)}
    return {
        "task_id": task.get("task_id", ""),
        "observed": 1,
        "observations": [obs],
        "artifact_size": len(body),
    }