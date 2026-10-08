"""Derivation identity: how the platform knows *why* something is true (spec 025 §32).

The obstacle this addresses is not missing code but missing identity. ``method_fingerprint``
appears on 22 call sites as a bare ``str``, and the convention that grew up around it is
visible in ``context/operators/adapters.py``: ``f"{self.id}@{self.version}"``. So methods
were named by hand, with no way to ask two questions that matter:

* Given the same method, inputs and numeric environment, did we already compute this? A
  cache key that omits any of the three replays a stale answer, which is not a performance
  bug -- it is a correctness bug wearing one.
* Given an output, which derivations produced it? Without that edge, a claim is
  unexplainable: it is asserted, and asserting is what this whole engine exists to avoid.

So a :class:`Derivation` is a *content address*. Its identity is the digest of the method,
the inputs, the environment and the output together. Omit the environment and a rerun
under different numerics returns the old answer. Omit the output and two different results
collide on one key. Both are silent.

The vocabulary conforms to the existing ``id@version`` convention rather than introducing
a second one. Determinism and numeric-mode metadata deliberately stay in the operator
registrations under ``context.operators.base`` -- this module is below that layer in
:data:`LAYER_ORDER`, so it cannot import it, and identity does not need it.

What this does not do: it does not prove a claim correct, only that the claim is
attributable and replayable. A wrong method with a sound fingerprint is still wrong.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MethodFingerprint",
    "NumericEnvironment",
    "Derivation",
    "DerivationGraph",
    "DerivationError",
    "DanglingParent",
    "DerivationCycle",
    "digest_of",
]


class DerivationError(ValueError):
    """A derivation is structurally unsound."""


class DanglingParent(DerivationError):
    """A derivation claims a parent that was never recorded."""


class DerivationCycle(DerivationError):
    """Adding this derivation would close a loop in the derivation graph."""


def digest_of(value: Any) -> str:
    """A stable digest of any JSON-shaped value.

    Sorted keys and no whitespace so that two equal values always agree, including across
    dict insertion order -- an identity that depended on insertion order would mint a new
    id for the same derivation on every rerun and defeat replay entirely.
    """
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MethodFingerprint:
    """``id@version``, the identity of the thing that produced a result.

    A bare string was not enough: ``"gluing.operator.v1"`` and a rewritten ``v2`` differ
    only in that suffix, and a record that stored the whole name could not tell "same
    method" from "method that happens to be spelled the same". Splitting the two makes
    the version a first-class thing to compare, so upgrading an operator is a visible
    change to every derivation it produced.
    """

    id: str
    version: str

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise DerivationError("method id must not be empty")
        if not self.version or not str(self.version).strip():
            raise DerivationError("method version must not be empty")
        if "@" in str(self.id):
            raise DerivationError(f"method id must not contain '@': {self.id!r}")

    @classmethod
    def parse(cls, text: str) -> MethodFingerprint:
        """Parse the platform's existing ``id@version`` spelling.

        No ``@`` is an error rather than a default version. Inventing ``v1`` here would
        let a malformed fingerprint pass as a specific one, and the whole point is that
        the version is known.
        """
        raw = str(text or "")
        if "@" not in raw:
            raise DerivationError(
                f"method fingerprint must be 'id@version', got {raw!r}"
            )
        method_id, _, version = raw.rpartition("@")
        return cls(method_id, version)

    def __str__(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def digest(self) -> str:
        return digest_of([self.id, self.version])


@dataclass(frozen=True)
class NumericEnvironment:
    """The numeric context a derivation ran under.

    Three reasons this is not optional. Some disciplines are only defined on a declared
    scale (``FLOAT_QUANTIZED`` means float output with no tolerance contract). Some
    operators quantize against a character limit, so truncating at 20 000 chars and at
    10 000 are different methods. And some need actual numbers to run at all -- thresholds
    and cutoffs -- whose absence must be visible rather than defaulted.

    Immutable and carrying ``bounded`` rather than a limit alone, so a caller cannot hold a
    limit and apply a different one. The immutability is what lets the environment go
    into a derivation's identity: a mutable environment in a content address would let the
    address change after the fact.
    """

    char_limit: int = 20_000
    values: Mapping[str, float | int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.char_limit <= 0:
            raise DerivationError("char_limit must be positive")

    @classmethod
    def coerce(cls, raw: Any, key: str | None = None) -> NumericEnvironment:
        """Build from whatever a caller had: a mapping, an instance, or nothing.

        An existing environment passes through unchanged, so ``coerce`` is safe to call on
        a value that may already be one. That matters because environment objects are
        threaded through operator options, and re-wrapping would produce an equal-but-
        distinct instance with a different identity.
        """
        if isinstance(raw, NumericEnvironment):
            return raw
        if raw is None:
            return cls()
        if isinstance(raw, Mapping):
            values = {str(k): v for k, v in raw.items()}
        else:
            values = {str(key or "value"): raw}
        for name, value in values.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise DerivationError(
                    f"numeric environment value {name!r} is not numeric: {value!r}"
                )
        return cls(values=dict(sorted(values.items())))

    def bounded(self, text: str) -> str:
        """Text as this environment would see it, truncated at ``char_limit``.

        Kept next to the limit so the two cannot drift. A limit stored apart from the
        function that applies it is a limit that is eventually wrong somewhere.
        """
        return str(text)[: self.char_limit]

    def with_value(self, key: str, value: float | int) -> NumericEnvironment:
        """A new environment with one value set. Does not mutate."""
        merged = dict(self.values)
        merged[str(key)] = value
        return type(self)(char_limit=self.char_limit, values=dict(sorted(merged.items())))

    @property
    def digest(self) -> str:
        return digest_of([self.char_limit, sorted(self.values.items())])


@dataclass(frozen=True)
class Derivation:
    """One "this output, because of these inputs, under these numerics".

    Content-addressed by :attr:`derivation_id`, which covers method, inputs, environment
    and output. That set is the minimum for replay: with any one of them missing, either a
    rerun returns the wrong answer or two distinct answers share an id.

    ``statement`` is the human-readable claim. It is carried but never hashed into the
    id, because it is a rendering of the derivation and two renderings of one derivation
    must not mint two identities.
    """

    method: MethodFingerprint
    inputs: tuple[str, ...] = ()
    output: str = ""
    statement: str = ""
    environment: NumericEnvironment = field(default_factory=NumericEnvironment)
    confidence: float | None = None
    parents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.output or not str(self.output).strip():
            raise DerivationError("a derivation must name the output it produced")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise DerivationError(f"confidence out of range: {self.confidence}")

    @property
    def derivation_id(self) -> str:
        # ``parents`` is in the digest because provenance is part of what the derivation
        # *is*. Leaving it out lets two derivations that agree on method, inputs,
        # environment and output but rest on different prior claims collapse onto one id --
        # and ``add`` would then read the second as a replay and silently keep the first
        # parent chain, which is exactly the explanation loss the graph exists to prevent.
        return digest_of(
            {
                "method": self.method.digest,
                "inputs": sorted(self.inputs),
                "environment": self.environment.digest,
                "output": self.output,
                "parents": sorted(self.parents),
            }
        )

    def supports(self, output: str) -> bool:
        """Whether this derivation produced ``output``."""
        return self.output == output


class DerivationGraph:
    """Recorded derivations, indexed by identity.

    Refuses a derivation whose parents are absent. Both refusals are about the same
    failure: a derivation resting on something the graph never recorded is an explanation
    with a hole in it, and "every output has a derivation" stops being a true statement.

    The graph is acyclic by construction rather than by check: a parent must already exist
    before a child can cite it, so the earliest node in any parent edge is necessarily
    parentless. Longer cycles are therefore unbuildable through :meth:`add`, and the only
    refusal needed is the direct one. A caller that loads ids from outside -- a database
    read, a future API -- must re-check acyclicity itself; insertion order is not available
    to it.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Derivation] = {}

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, derivation_id: object) -> bool:
        return str(derivation_id) in self._nodes

    def add(self, derivation: Derivation) -> str:
        """Record a derivation. Returns its id. Idempotent for identical content."""
        derivation_id = derivation.derivation_id
        existing = self._nodes.get(derivation_id)
        if existing is not None:
            # Same id means same content, because the id *is* the content digest. Two
            # differing derivations cannot share one, so this is a replay, not a conflict.
            return derivation_id

        missing = [p for p in derivation.parents if p not in self._nodes]
        if missing:
            raise DanglingParent(
                f"derivation {derivation_id[:12]} names {len(missing)} unknown parent(s): "
                f"{[p[:12] for p in missing]}"
            )
        if derivation_id in derivation.parents:
            raise DerivationCycle("a derivation cannot be its own parent")

        self._nodes[derivation_id] = derivation
        return derivation_id

    def get(self, derivation_id: str) -> Derivation | None:
        return self._nodes.get(str(derivation_id))

    def by_output(self, output: str) -> tuple[Derivation, ...]:
        """Every derivation that produced ``output``, oldest first."""
        return tuple(n for n in self._nodes.values() if n.supports(output))

    def ancestors(self, derivation_id: str) -> tuple[Derivation, ...]:
        """What this derivation rests on, breadth-first."""
        seen: set[str] = set()
        found: list[Derivation] = []
        node = self._nodes.get(str(derivation_id))
        frontier = list(node.parents) if node is not None else []
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            node = self._nodes.get(current)
            if node is not None:
                found.append(node)
                frontier.extend(node.parents)
        return tuple(found)

    def statements_for(self, output: str) -> tuple[str, ...]:
        """The rendered claims behind ``output`` -- the answer to "why do you say that?"."""
        return tuple(d.statement for d in self.by_output(output) if d.statement)

    def leaves(self) -> tuple[Derivation, ...]:
        """Derivations nothing further builds on: where the explanations stop."""
        referenced = {p for n in self._nodes.values() for p in n.parents}
        return tuple(n for i, n in self._nodes.items() if i not in referenced)

    def roots(self) -> tuple[Derivation, ...]:
        """Derivations that rest on no earlier derivation."""
        return tuple(n for n in self._nodes.values() if not n.parents)

    def methods(self) -> tuple[str, ...]:
        """Distinct method fingerprints used, sorted -- so a version bump is visible."""
        return tuple(sorted({str(n.method) for n in self._nodes.values()}))

    def add_all(self, derivations: Iterable[Derivation]) -> int:
        return sum(1 for d in derivations if self.add(d))