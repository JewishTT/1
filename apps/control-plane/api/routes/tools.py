"""Maltego-style entity→tool catalog API for the SpecOps frontend (hermetic).

Lists which recon/OSINT/discovery tools apply per entity type and enqueues a
run as an SSE ``specops.tool_requested`` event. Recon/discovery ONLY — no
harassment, flooding or attack-launching tooling. Enqueueing is hermetic:
nothing is executed in-process (vendored CLI workers stay init specs, the
same philosophy as the zero layer's ``CommandSpec``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant
from api.sse import hub
from services.tool_catalog import all_tools, tool, tools_for

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolEnqueue(BaseModel):
    entity_type: str
    entity_value: str
    entity_id: str | None = None


@router.get("")
async def list_tools(
    entity_type: str | None = None,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Catalog of applicable tools, optionally narrowed to one entity type."""
    specs = tools_for(entity_type) if entity_type else all_tools()
    return {"tools": [s.as_dict() for s in specs], "tenant_id": ctx.tenant_id}


@router.post("/{tool_id}/enqueue")
async def enqueue_tool(
    tool_id: str,
    body: ToolEnqueue,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Enqueue a hermetic tool run: publish ``specops.tool_requested`` only."""
    spec = tool(tool_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if body.entity_type not in spec.entity_types:
        raise HTTPException(status_code=422, detail="entity_type not supported by this tool")
    hub.publish(
        "specops.tool_requested",
        {
            "tool_id": spec.tool_id,
            "tenant_id": ctx.tenant_id,
            "event": "specops.tool_requested",
            "entity_type": body.entity_type,
            "entity_value": body.entity_value,
            "entity_id": body.entity_id,
        },
    )
    return {
        "run": {
            "tool_id": spec.tool_id,
            "entity_type": body.entity_type,
            "entity_value": body.entity_value,
            "entity_id": body.entity_id,
            "status": "QUEUED",
            "command": list(spec.command_template),
        },
        "event": "specops.tool_requested",
    }