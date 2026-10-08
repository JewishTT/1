"""The SQL type vocabulary and the Python one cannot drift (spec 025 §32).

``db.schema.ENTITY_TYPE_VALUES`` is a copy: a CHECK constraint needs a literal SQL string,
so the list cannot simply be imported from ``domain.ontology``. A copy is exactly the kind of
thing that goes stale -- somebody adds an ``EntityType``, the constraint does not, and every
write of the new type fails with a CheckViolation nobody can explain.

This is the test that makes the copy safe. It compares both directions and names the drift,
because a silent divergence between "what the platform may write" and "what the database
accepts" is a bug that surfaces as a production write failure hours later.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "control-plane"))

from db.schema import ARTIFACT_KIND_VALUES, ENTITY_TYPE_VALUES
from domain.ontology import EntityType, StaticArtifactKind

pytestmark = pytest.mark.contract

# ``parents[0]``=tests, [1]=contract, [2]=science, [3]=apps -- so control-plane is a sibling.
MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "control-plane" / "db" / "migrations" / "versions"
    / "023_derivation_enforcement.py"
)


class TestVocabularyMatches:
    def test_entity_types_match_the_orm_constraint(self) -> None:
        declared = {t.value for t in EntityType}
        constrained = set(ENTITY_TYPE_VALUES)
        assert declared == constrained, (
            "ENTITY_TYPE_VALUES в db/schema.py разошёлся с domain.ontology:\n"
            f"  только в онтологии: {sorted(declared - constrained)}\n"
            f"  только в CHECK:     {sorted(constrained - declared)}"
        )

    def test_artifact_kinds_match_the_orm_constraint(self) -> None:
        declared = {t.value for t in StaticArtifactKind}
        assert declared == set(ARTIFACT_KIND_VALUES), (
            "ARTIFACT_KIND_VALUES разошёлся с StaticArtifactKind:\n"
            f"  только в онтологии: {sorted(declared - set(ARTIFACT_KIND_VALUES))}\n"
            f"  только в CHECK:     {sorted(set(ARTIFACT_KIND_VALUES) - declared)}"
        )


class TestMigrationAgrees:
    def _migration_text(self) -> str:
        if not MIGRATION.exists():
            pytest.skip(f"{MIGRATION} не найден")
        return MIGRATION.read_text(encoding="utf-8")

    def test_the_migration_declares_the_same_types(self) -> None:
        """Two copies of one vocabulary is already too many; three is not acceptable.

        The ORM list and the migration list exist because ``create_all`` and ``alembic
        upgrade`` are separate install paths, and both were already a problem once. They are
        pinned to the same values here rather than generated, so a diff shows what changed.
        """
        source = self._migration_text()

        def values_of(name: str) -> set[str]:
            block = source.split(name)[1]
            end = min(
                (i for marker in ("ARTIFACT_KIND_VALUES", "def upgrade")
                 if (i := block.find(marker)) > 0),
                default=len(block),
            )
            return set(re.findall(r'"([a-z_0-9]+)"', block[:end]))

        # Compared separately, because the two lists mean different things: mixing them let
        # an artifact kind look like an entity type and the difference between the two files
        # vanish into one comparison.
        assert values_of("ENTITY_TYPE_VALUES") == set(ENTITY_TYPE_VALUES), (
            "миграция 023 и db/schema.py расходятся по EntityType:\n"
            f"  только в миграции: {sorted(values_of('ENTITY_TYPE_VALUES') - set(ENTITY_TYPE_VALUES))}\n"
            f"  только в schema.py: {sorted(set(ENTITY_TYPE_VALUES) - values_of('ENTITY_TYPE_VALUES'))}"
        )
        assert values_of("ARTIFACT_KIND_VALUES") == set(ARTIFACT_KIND_VALUES), (
            "миграция 023 и db/schema.py расходятся по StaticArtifactKind:\n"
            f"  только в миграции: {sorted(values_of('ARTIFACT_KIND_VALUES') - set(ARTIFACT_KIND_VALUES))}\n"
            f"  только в schema.py: {sorted(set(ARTIFACT_KIND_VALUES) - values_of('ARTIFACT_KIND_VALUES'))}"
        )

    def test_the_migration_is_importable_and_wired(self) -> None:
        spec = importlib.util.spec_from_file_location("m023", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "023_derivation_enforcement"
        assert module.down_revision == "022_context_fabric"
        assert callable(module.upgrade) and callable(module.downgrade)

    def test_downgrade_removes_everything_upgrade_created(self) -> None:
        source = self._migration_text()
        created = set(re.findall(r'op\.create_table\(\s*\n?\s*"(\w+)"', source))
        created |= set(re.findall(r'create_table\(\s*\n\s*"(\w+)"', source))
        down = source.split("def downgrade")[1]
        for table in created:
            assert f'"{table}"' in down, f"downgrade не убирает {table}"


class TestDerivedTypesStayOnTheEntityAxis:
    def test_value_kinds_are_not_entity_types(self) -> None:
        """A timestamp is a value on a claim, not a thing that inherits ``Thing``.

        The live sweep found 99 fields declared ``timestamp``/``description`` across the 145
        sources. Letting those names into ``EntityType`` would have written
        ``entity_type='timestamp'`` into a column that means "what kind of thing is this",
        and let a scope lattice claim a moment is an entity.
        """
        from domain.ontology import VALUE_KINDS

        # ``unknown`` is excluded on purpose: it is the absence of a classification and
        # belongs to both axes. Everything else must land on exactly one.
        overlap = (VALUE_KINDS & {t.value for t in EntityType}) - {"unknown"}
        assert not overlap, f"значение названо сущностью: {sorted(overlap)}"

    def test_the_two_axes_are_disjoint_and_complete_for_declared_names(self) -> None:
        from domain.ontology import VALUE_KINDS

        entity = {t.value for t in EntityType}
        assert not ((VALUE_KINDS & entity) - {"unknown"})
        assert VALUE_KINDS, "ось значений пуста"
        assert len(entity) > 40, "ось сущностей подозрительно мала"