"""Contract: a claim is attributable and replayable, or it is not stored (spec 025 §32).

``method_fingerprint`` was free text on 22 call sites, so two questions had no answer:
has this exact computation been done before, and what produced this output? Both matter
more than they look. A cache key that omits the numeric environment returns a stale answer
under different numerics -- a correctness bug wearing a performance costume. An identity
that omits the output gives two different results one key.

The properties below are the contract:

* **Deterministic** -- same method, inputs, environment and output, same id.
* **Distinguishing** -- any of those four changing, different id.
* **Replayable** -- re-adding an identical derivation is a no-op, not a duplicate.
* **Attributable** -- every output's derivations can be read back as statements.
* **Acyclic and reachable** -- no dangling parent, no loop, no unreachable explanation.

What is deliberately *not* claimed: that a derivation is correct. A wrong method with a
sound fingerprint is still wrong. Identity proves attribution, not truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.derivation import (
    DanglingParent,
    Derivation,
    DerivationCycle,
    DerivationError,
    DerivationGraph,
    MethodFingerprint,
    NumericEnvironment,
    digest_of,
)

pytestmark = pytest.mark.contract

METHOD = MethodFingerprint.parse("gluing.operator@v1")
ENV = NumericEnvironment.coerce({"threshold": 0.5})
A, B, C = "a" * 64, "b" * 64, "c" * 64


def derive(output: str = B, **kwargs) -> Derivation:
    kwargs.setdefault("inputs", (A,))
    kwargs.setdefault("environment", ENV)
    return Derivation(MethodFingerprint(kwargs.pop("method", "gluing.operator"), "v1"),
                      output=output, **kwargs)


class TestMethodFingerprint:
    def test_it_matches_the_platform_spelling(self) -> None:
        assert str(METHOD) == "gluing.operator@v1"

    def test_it_round_trips(self) -> None:
        assert MethodFingerprint.parse(str(METHOD)) == METHOD

    def test_a_missing_version_is_refused_rather_than_defaulted(self) -> None:
        # Defaulting to v1 would let a malformed fingerprint pass as a specific one, and
        # the version being known is the entire reason the type exists.
        with pytest.raises(DerivationError):
            MethodFingerprint.parse("no-version")

    def test_an_at_sign_inside_the_id_is_refused(self) -> None:
        with pytest.raises(DerivationError):
            MethodFingerprint("bad@id", "v1")

    def test_an_empty_version_is_refused(self) -> None:
        with pytest.raises(DerivationError):
            MethodFingerprint("gluing.operator", "")

    def test_upgrading_the_method_changes_the_fingerprint(self) -> None:
        assert MethodFingerprint("gluing.operator", "v1").digest != (
            MethodFingerprint("gluing.operator", "v2").digest
        )


class TestNumericEnvironment:
    def test_coerce_passes_an_existing_environment_through(self) -> None:
        # Rewrapping would yield an equal-but-distinct instance with a different identity,
        # and this gets threaded through operator options.
        assert NumericEnvironment.coerce(ENV) is ENV

    def test_it_refuses_non_numeric_values(self) -> None:
        with pytest.raises(DerivationError):
            NumericEnvironment.coerce({"threshold": "high"})

    def test_a_bool_is_not_a_number_here(self) -> None:
        # bool is an int subclass, so without this a flag silently became a magnitude.
        with pytest.raises(DerivationError):
            NumericEnvironment.coerce({"flag": True})

    def test_with_value_does_not_mutate(self) -> None:
        moved = ENV.with_value("threshold", 0.9)
        assert ENV.values["threshold"] == 0.5
        assert moved.values["threshold"] == 0.9

    def test_the_limit_lives_next_to_the_truncation(self) -> None:
        assert NumericEnvironment(char_limit=10).bounded("x" * 50) == "x" * 10

    def test_a_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(DerivationError):
            NumericEnvironment(char_limit=0)


class TestIdentityIsDeterministic:
    def test_the_same_derivation_has_the_same_id(self) -> None:
        assert derive().derivation_id == derive().derivation_id

    def test_digest_does_not_depend_on_dict_ordering(self) -> None:
        assert digest_of({"a": 1, "b": 2}) == digest_of({"b": 2, "a": 1})


class TestIdentityDistinguishes:
    def test_a_different_output_is_a_different_derivation(self) -> None:
        assert derive(B).derivation_id != derive(C).derivation_id

    def test_different_inputs_are_a_different_derivation(self) -> None:
        assert derive(inputs=(A,)).derivation_id != derive(inputs=(C,)).derivation_id

    def test_a_different_method_is_a_different_derivation(self) -> None:
        assert derive().derivation_id != derive(method="other.operator").derivation_id

    def test_a_different_environment_is_a_different_derivation(self) -> None:
        # The reason environment is in the identity: same inputs, same method, different
        # numerics is a different answer, and reusing the old one would be wrong.
        moved = ENV.with_value("threshold", 0.9)
        assert derive().derivation_id != derive(environment=moved).derivation_id

    def test_a_changed_char_limit_is_a_different_derivation(self) -> None:
        tight = NumericEnvironment(char_limit=1_000, values=dict(ENV.values))
        assert derive().derivation_id != derive(environment=tight).derivation_id

    def test_input_order_does_not_change_identity(self) -> None:
        assert derive(inputs=(A, C)).derivation_id == derive(inputs=(C, A)).derivation_id

    def test_different_parents_are_a_different_derivation(self) -> None:
        # Provenance is part of what the derivation is. Collapsing two parent chains onto
        # one id would make ``add`` read the second as a replay and silently keep the
        # first -- the explanation loss the graph exists to prevent.
        graph = DerivationGraph()
        other = Derivation(METHOD, inputs=(C,), output=A)
        left = Derivation(METHOD, inputs=(A,), output=B, parents=())
        right = Derivation(METHOD, inputs=(A,), output=B,
                           parents=(other.derivation_id,))
        assert left.derivation_id != right.derivation_id
        graph.add(left)
        graph.add(other)
        graph.add(right)
        assert len(graph) == 3

    def test_the_statement_is_not_part_of_identity(self) -> None:
        # The statement is a rendering; two renderings of one derivation are one thing.
        assert (derive(statement="A -> B").derivation_id
                == derive(statement="другая формулировка").derivation_id)


class TestDerivationIsSound:
    def test_an_unnamed_output_is_refused(self) -> None:
        with pytest.raises(DerivationError):
            Derivation(METHOD, inputs=(A,), output="  ")

    def test_confidence_outside_the_unit_interval_is_refused(self) -> None:
        with pytest.raises(DerivationError):
            Derivation(METHOD, inputs=(A,), output=B, confidence=1.4)


class TestGraphReplayAndAttribution:
    def test_adding_the_same_derivation_twice_is_a_replay(self) -> None:
        graph = DerivationGraph()
        first = graph.add(derive())
        assert graph.add(derive()) == first
        assert len(graph) == 1

    def test_outputs_are_attributable(self) -> None:
        graph = DerivationGraph()
        graph.add(derive(B, statement="A -> B"))
        assert graph.statements_for(B) == ("A -> B",)

    def test_an_unproduced_output_has_no_statements(self) -> None:
        assert DerivationGraph().statements_for(C) == ()

    def test_method_versions_are_visible_in_the_graph(self) -> None:
        graph = DerivationGraph()
        graph.add(derive(B))
        graph.add(derive(C, method="other.operator"))
        assert graph.methods() == ("gluing.operator@v1", "other.operator@v1")


class TestGraphRefusesUnreachableExplanations:
    def test_a_dangling_parent_is_refused(self) -> None:
        with pytest.raises(DanglingParent):
            DerivationGraph().add(derive(parents=("unknown-id",)))

    def test_a_self_parent_is_not_constructible(self) -> None:
        # ``parents`` is in the id digest, so a derivation citing itself would need its
        # own digest as an input to itself. The explicit check in ``add`` stays as a guard
        # for ids that arrive from outside, not because ``add`` can reach it.
        graph = DerivationGraph()
        node = derive()
        graph.add(node)
        clone = Derivation(METHOD, inputs=node.inputs, output=node.output,
                           parents=(node.derivation_id,))
        assert clone.derivation_id != node.derivation_id

    def test_ancestors_are_walkable(self) -> None:
        graph = DerivationGraph()
        base = derive(B)
        graph.add(base)
        mid = Derivation(METHOD, inputs=(B,), output=C, parents=(base.derivation_id,))
        graph.add(mid)
        top = Derivation(METHOD, inputs=(C,), output=A, parents=(mid.derivation_id,))
        graph.add(top)
        assert len(graph.ancestors(top.derivation_id)) == 2
        assert len(graph.ancestors(mid.derivation_id)) == 1
        assert graph.ancestors("nonexistent") == ()

    def test_roots_and_leaves_bound_the_chain(self) -> None:
        graph = DerivationGraph()
        first = graph.add(derive(B))
        graph.add(derive(C, parents=(first,)))
        assert len(graph.roots()) == 1
        assert len(graph.leaves()) == 1
