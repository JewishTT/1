"""Feature 024 T018 -- layer boundary guard.

Constitution: a layer imports only downward, and everything that writes goes
through a contract. The platform had no mechanical enforcement of either: no
import-linter, no architecture contract test, no ownership matrix. Boundaries were
a convention that grep could see through, and the convention was already broken.

This module is the guard. It parses the real import graph with ``ast`` -- no
third-party import linter, no regex over source text -- and reports any layer that
reaches upward or sideways into a store it does not own.

Run as a script for a readable report; import ``find_violations`` for assertions.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APPS = REPO_ROOT / "apps"

#: Layers, ordered from the substrate upward. An import may only go to a *lower*
#: index. Same-index is allowed only when the target is a sibling within the same
#: layer -- cross-app same-layer imports are reported separately.
LAYER_ORDER = ["shared", "interpretation", "admission", "projection", "control-plane", "science"]

#: The event substrate is the one legitimate upward-facing dependency: producers in
#: every layer publish events, and the contract lives in `shared`.
EVENT_CONTRACT_MODULES = {"events", "ids", "config", "domain"}

#: Store-owning modules, keyed by the layer that owns them. Importing one from a
#: layer that does not own it is a cross-layer write, which is the exact defect
#: FR-010 forbids. Directories are matched on the `apps/<app>/` prefix.
OWNED_STORES: dict[str, tuple[str, ...]] = {
    "control-plane": ("db", "workflows"),
}

#: Alias used in the repo to keep `apps/shared` ahead of conflicting directories.
SHIM_MODULES = {"path_shim"}


@dataclass(frozen=True)
class Violation:
    layer: str
    source: str
    line: int
    target_app: str
    target_module: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return (
            f"{self.source}:{self.line} [{self.layer}] {self.kind} -> "
            f"{self.target_app}/{self.target_module}: {self.detail}"
        )


def _iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _app_of(path: Path, root: Path) -> str | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def _imported_modules(tree: ast.AST) -> Iterator[tuple[str, int]]:
    """Yield (dotted module, line) for every import in the file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: stays inside the layer by definition
                continue
            if node.module:
                yield node.module, node.lineno


def _resolve_app(module: str) -> str | None:
    """Map an absolute dotted module onto the app it lives in, if any."""
    head = module.split(".", 1)[0]
    if head == "apps" and "." in module:
        parts = module.split(".")
        if len(parts) > 1:
            return parts[1]
        return None
    return None


def find_violations(apps_root: Path | None = None) -> list[Violation]:
    """Every layer-boundary violation found under ``apps_root``."""
    root = apps_root or APPS
    out: list[Violation] = []

    for path in _iter_python_files(root):
        app = _app_of(path, root)
        if app is None:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue

        try:
            rel_source = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel_source = path.name
        for module, line in _imported_modules(tree):
            if module in SHIM_MODULES:
                out.append(
                    Violation(
                        app, rel_source, line, "", module, "shim",
                        "sys.path manipulation instead of a declared dependency",
                    )
                )
                continue

            target_app = _resolve_app(module)
            if target_app is None:
                # Flat imports (`events.kafka`) are resolved against sys.path and can
                # come from any app; only flag the ones that reach a store directly.
                head = module.split(".", 1)[0]
                for owner, owned in OWNED_STORES.items():
                    if head in owned and owner != app:
                        out.append(
                            Violation(
                                app, rel_source, line, owner, module, "cross-layer-store",
                                f"`{head}` is owned by {owner}; {app} must go through a contract",
                            )
                        )
                continue

            if target_app not in LAYER_ORDER:
                continue
            if target_app == app:
                continue

            src_i = LAYER_ORDER.index(app)
            dst_i = LAYER_ORDER.index(target_app)

            if module.split(".", 1)[0] in EVENT_CONTRACT_MODULES and dst_i < src_i:
                # Downward import of a lower layer: correct.
                continue

            if dst_i < src_i:
                continue  # downward import: allowed

            kind = "cross-layer-import"
            detail = (
                f"{app} imports {target_app}, which is at the same or a higher level "
                f"({' > '.join(LAYER_ORDER[min(src_i, dst_i) : max(src_i, dst_i) + 1])})"
            )
            out.append(Violation(app, rel_source, line, target_app, module, kind, detail))

    return sorted(out, key=lambda v: (v.source, v.line))


def main() -> int:
    violations = find_violations()
    if not violations:
        print("layer boundaries: clean")
        return 0
    print(f"layer boundaries: {len(violations)} violation(s)\n")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())