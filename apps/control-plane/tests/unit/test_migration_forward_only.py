"""Migration-graph regressions for forward-only schema changes (feature 015).

Two invariants are enforced here:

1. An already-released revision is never edited. Revision 014 was applied to live
   databases and was repeatedly modified afterwards, which silently prevented
   deployed databases from ever receiving the new tables and columns. Its content
   is pinned by digest so any future edit fails loudly.
2. The revision graph is linear. A branch would mean two heads, and "upgrade
   head" would then be ambiguous for an operator.

Digest values cover file content only; they are not a substitute for verifying
both install paths against a live database.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations" / "versions"

# SHA-256 of each released revision file, recorded when that revision was
# published. Adding a new revision is expected; editing an existing one is not.
RELEASED_DIGESTS: dict[str, str] = {
    "014_temporal_materialization.py": (
        "27b606f3b5458bdac33e64351a5509389ccc808cede244f29539cdf40f55a09b"
    ),
}

_REVISION = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)


def _parse(path: Path) -> tuple[str, str | None]:
    text = path.read_text(encoding="utf-8")
    revision = _REVISION.search(text)
    assert revision, f"{path.name} has no revision identifier"
    down_match = _DOWN_REVISION.search(text)
    assert down_match, f"{path.name} has no down_revision"
    raw = down_match.group(1).strip()
    if raw == "None":
        return revision.group(1), None
    quoted = re.match(r'^["\']([^"\']+)["\']$', raw)
    assert quoted, f"{path.name} has an unparseable down_revision: {raw!r}"
    return revision.group(1), quoted.group(1)


def _content_digest(path: Path) -> str:
    """SHA-256 of file content with line endings normalized.

    The repository sets ``core.autocrlf=true``, so the same committed file is
    CRLF in a Windows working tree and LF on CI. Hashing raw bytes would make
    this regression fail spuriously on one platform or the other, so newlines are
    normalized before hashing. Line-ending-only churn is not the edit this test
    exists to catch; a content change is.
    """
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_released_revisions_are_not_edited() -> None:
    """A released revision must keep identical content (FR-033)."""
    for filename, expected in RELEASED_DIGESTS.items():
        path = VERSIONS_DIR / filename
        assert path.exists(), f"released revision missing: {filename}"
        actual = _content_digest(path)
        assert actual == expected, (
            f"{filename} was modified after release "
            f"(expected {expected}, got {actual}). Released migrations are "
            f"immutable: add a new forward-only revision instead."
        )


def test_revision_graph_is_linear_and_has_a_single_head() -> None:
    """Exactly one root and one head; no branching (FR-033)."""
    graph: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        revision, down = _parse(path)
        assert revision not in graph, f"duplicate revision id: {revision}"
        graph[revision] = down

    roots = [rev for rev, down in graph.items() if down is None]
    assert len(roots) == 1, f"expected exactly one root revision, got {roots}"

    children: dict[str, list[str]] = {}
    for rev, down in graph.items():
        if down is not None:
            assert down in graph, f"{rev} points at unknown parent {down}"
            children.setdefault(down, []).append(rev)
    for parent, kids in children.items():
        assert len(kids) == 1, f"revision {parent} has multiple children: {kids}"

    heads = [rev for rev in graph if rev not in children]
    assert len(heads) == 1, f"expected exactly one head revision, got {heads}"


def test_worldline_revision_follows_temporal_materialization() -> None:
    """015 must be a child of 014, not a replacement or a sibling root."""
    revision, down = _parse(VERSIONS_DIR / "015_worldline_reconstruction.py")
    assert revision == "015_worldline_reconstruction"
    assert down == "014_temporal_materialization"


def test_worldline_migration_creates_new_tables_before_indexing_them() -> None:
    """Backfill must precede the partial unique index it feeds (T007).

    Creating ``uq_materialization_outbox_active`` before the backfill would let
    NULL-fingerprinted rows slip through, leaving exactly the pre-existing rows
    the index exists to constrain unconstrained.
    """
    text = (VERSIONS_DIR / "015_worldline_reconstruction.py").read_text(encoding="utf-8")
    # Anchor on the upgrade() body: the backfill helper is *defined* above it,
    # so a whole-file search would match the definition instead of the call.
    upgrade = text[text.index("def upgrade()"):]
    add_column = upgrade.index('sa.Column("identity_fingerprint"')
    backfill = upgrade.index("_backfill_identity_fingerprints()")
    index = upgrade.index('"uq_materialization_outbox_active"')
    assert add_column < backfill < index, (
        "revision 015 must add identity_fingerprint, then backfill, then create "
        "the unique index"
    )


def test_migration_env_resolves_a_database_url() -> None:
    """`alembic upgrade` must resolve a URL without editing alembic.ini.

    The ini ships an empty ``sqlalchemy.url`` placeholder, so an env that never
    injects one fails with "Connection, url, or dialect_name is required" and
    the migration path can never be exercised at all.
    """
    env = (VERSIONS_DIR.parent / "env.py").read_text(encoding="utf-8")
    assert "get_settings" in env, "migrations/env.py must resolve the DSN from settings"
    assert "postgres.dsn" in env, "migrations/env.py must use the application DSN"
