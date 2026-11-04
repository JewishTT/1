"""Fail if known local/runtime artifacts have entered the tracked Git tree."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def classify_tracked_path(path: str) -> str | None:
    """Return the reason a tracked path violates repository hygiene, else None."""
    normalized = path.replace("\\", "/").lstrip("./")
    parts = PurePosixPath(normalized).parts
    if not parts:
        return None
    root = parts[0]

    if root in {"tmp", "logs", "pytest-of-tim"} or root.startswith(("tmp.", "tmpa", "pytest-of-")):
        return "root-level local test or scratch output"
    if root.startswith(("pip-metadata-", "pip-unpack-")):
        return "pip temporary installation workspace"
    if len(parts) == 1 and re.fullmatch(r"(?:probe|scratch)_[^/]+\.py", root):
        return "one-off root probe; move maintained checks under tools/ or tests/"
    if normalized.startswith("apps/webapp/tmp/"):
        return "local screenshot or test output; use the maintained Playwright CI artifact"
    if len(parts) == 2 and parts[0] == "apps/webapp" and re.fullmatch(r"probe.*\.mjs", parts[1], re.I):
        return "ad-hoc browser probe; maintain regression coverage under apps/webapp/scripts/"
    if len(parts) == 2 and parts[0] == "apps/webapp" and re.fullmatch(r"shot[2-9]\.mjs", parts[1], re.I):
        return "superseded one-off screenshot script"
    if normalized.startswith("apps/acquisition/artifacts/acquisition-integration/"):
        return "generated live acceptance output; CI uploads this as a workflow artifact"
    if normalized.startswith("apps/interpretation/artifacts/acquisition-integration/"):
        return "generated downstream acceptance output; CI uploads reproducible evidence"
    if normalized.startswith("apps/interpretation/artifacts/interpretation/"):
        return "generated parser proof output; keep the proof script, not its run result"
    return None


def tracked_paths(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [item.decode("utf-8", errors="replace") for item in result.stdout.split(b"\0") if item]


def violations(root: Path = ROOT) -> list[dict[str, str]]:
    return [
        {"path": path, "reason": reason}
        for path in tracked_paths(root)
        if (reason := classify_tracked_path(path))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero if tracked scratch files exist")
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    args = parser.parse_args(argv)
    try:
        findings = violations()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"repository hygiene check failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"ok": not findings, "violations": findings}, indent=2))
    elif findings:
        print("Tracked local/runtime artifacts found:")
        for item in findings:
            print(f"  {item['path']}: {item['reason']}")
        print("Remove the output, add the correct ignore rule, and keep reproducible test code.")
    else:
        print("Repository hygiene: clean tracked tree.")
    return 1 if args.check and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
