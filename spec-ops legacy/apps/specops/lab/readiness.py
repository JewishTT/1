"""Capability/readiness matrix for the Red-Team Lab.

The matrix is the department's honesty surface. A donor that cannot be integrated, a
missing credential or an absent Caldera service is named here; none of them is rendered
as a zero or silently defaulted. The lab itself is no longer a lab-only exception:
targets and recipients are gated by a confirmed RoE, not by a hard-coded allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path

from specops.lab.phishingclub import config as phishingclub_config

REPO_ROOT = Path(__file__).resolve().parents[3]
DONOR_REGISTRY = REPO_ROOT / "donors" / "registry.yaml"
DONOR_PATH = REPO_ROOT / "donors" / "phishingclub"
ATTRIBUTION = DONOR_PATH / "ATTRIBUTION.md"


def _phishingclub_entry() -> dict:
    if not DONOR_REGISTRY.is_file():
        return {}
    text = DONOR_REGISTRY.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        entries = data.get("donors", data) if isinstance(data, dict) else data
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("id") == "phishingclub":
                    return entry
    except Exception:  # noqa: BLE001 - fallback parser below
        pass
    match = re.search(r"^- id: phishingclub\s*$", text, re.MULTILINE)
    if not match:
        return {}
    start = match.start()
    next_match = re.search(r"^- id: ", text[start + 1 :], re.MULTILINE)
    block = text[start : start + 1 + next_match.start()] if next_match else text[start:]
    entry: dict[str, str | None] = {}
    for key in ("path", "upstream", "version", "license", "license_source", "status", "role"):
        found = re.search(rf"^\s+{key}:\s*(.+)$", block, re.MULTILINE)
        if found:
            value = found.group(1).strip().strip("'\"")
            entry[key] = None if value in {"null", "~"} else value
    return entry


def donor_state() -> dict:
    entry = _phishingclub_entry()
    status = str(entry.get("status") or "missing")
    version = entry.get("version")
    service = phishingclub_config()
    blockers: list[str] = []
    if not entry:
        blockers.append("donors/registry.yaml has no phishingclub entry")
    if status != "verified":
        blockers.append("donor registry status is not 'verified'")
    if not version:
        blockers.append("upstream revision is not pinned")
    if not ATTRIBUTION.is_file():
        blockers.append("donors/phishingclub/ATTRIBUTION.md is missing")
    return {
        "id": "phishingclub",
        "path": entry.get("path") or "donors/phishingclub",
        "status": status,
        "version": version,
        "license": entry.get("license") or "unknown",
        "license_source": entry.get("license_source"),
        "attribution": ATTRIBUTION.is_file(),
        "blockers": blockers,
        "adapter_served": True,
        "service_url": service["base_url"],
        "console_url": service["console_url"],
        "api_key_configured": service["api_key_configured"],
    }


def readiness(
    *,
    lab: dict,
    key_status: dict,
    emulation_plans: int,
    counts: dict[str, int],
) -> dict:
    donor = donor_state()
    mode_row = {
        "capability": "red-team mode",
        "state": "ready",
        "detail": "full mode · RoE-gated",
        "missing": [],
    }
    donor_row = {
        "capability": "phishingclub adapter",
        "state": "blocked" if donor["blockers"] else "ready",
        "detail": f"status={donor['status']} version={donor['version']} service={donor['service_url']}",
        "missing": list(donor["blockers"]),
    }
    encryption_row = {
        "capability": "artifact encryption",
        "state": "ready" if key_status["ready"] else "blocked",
        "detail": f"{key_status['algorithm']} · key_source={key_status['key_source']}",
        "missing": [] if key_status["ready"] else [key_status.get("error") or "artifact key unavailable"],
    }
    lab_row = {
        "capability": "red-team boundary",
        "state": "ready" if lab["status"] == "ready" else "blocked",
        "detail": f"{lab['status']} · egress={lab['egress_policy']}",
        "missing": [] if lab["status"] == "ready" else [f"lab status is {lab['status']}"],
    }
    caldera_row = {
        "capability": "caldera / AEL spine",
        "state": "ready" if emulation_plans else "blocked",
        "detail": f"{emulation_plans} plan(s) loaded from donor libraries",
        "missing": [] if emulation_plans else ["no Caldera/AEL plans loaded from donors/ael or donors/adversary_emulation_library"],
    }
    rows = [mode_row, donor_row, encryption_row, lab_row, caldera_row]
    blockers: list[str] = []
    for row in rows:
        for missing in row["missing"]:
            blockers.append(f"{row['capability']}: {missing}")
    blockers = list(dict.fromkeys(blockers))
    return {
        "donor": donor,
        "encryption": key_status,
        "full_red_team_enabled": True,
        "matrix": rows,
        "blockers": blockers,
        "counts": counts,
    }
