"""Evidence-only on-chain transaction dependency DAG.

This is a deterministic projection of explicitly observed transaction references.
It does not infer ownership, movement, change outputs, bridge relationships or
transaction ancestry from amounts, timestamps, labels or address similarity.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Literal

Chain = Literal["bitcoin", "ethereum", "tron"]
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ETH_HASH = re.compile(r"^0x[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class TransactionRef:
    chain: Chain
    network: str
    txid: str

    def __post_init__(self) -> None:
        if self.chain not in {"bitcoin", "ethereum", "tron"}:
            raise ValueError(f"unsupported chain: {self.chain}")
        network = self.network.strip().lower()
        txid = self.txid.strip().lower()
        if not network:
            raise ValueError("network is required; mainnet/testnet must not be conflated")
        valid = bool(_ETH_HASH.fullmatch(txid)) if self.chain == "ethereum" else bool(_HEX_64.fullmatch(txid))
        if not valid:
            raise ValueError(f"invalid {self.chain} transaction id: {self.txid!r}")
        object.__setattr__(self, "network", network)
        object.__setattr__(self, "txid", txid)


@dataclass(frozen=True)
class ObservedTransaction:
    ref: TransactionRef
    observation_id: str
    record_digest: str
    parent_refs: tuple[TransactionRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        digest = self.record_digest.strip().lower()
        if not _HEX_64.fullmatch(digest):
            raise ValueError("record_digest must be a SHA-256 hex digest")
        object.__setattr__(self, "observation_id", self.observation_id.strip())
        object.__setattr__(self, "record_digest", digest)
        object.__setattr__(self, "parent_refs", tuple(sorted(set(self.parent_refs))))


@dataclass(frozen=True, order=True)
class TransactionEdge:
    parent: TransactionRef
    child: TransactionRef
    observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class TransactionNode:
    ref: TransactionRef
    observation_ids: tuple[str, ...]
    record_digests: tuple[str, ...]

    @property
    def conflicting(self) -> bool:
        return len(self.record_digests) > 1


@dataclass(frozen=True, order=True)
class MissingParent:
    child: TransactionRef
    parent: TransactionRef


@dataclass(frozen=True, order=True)
class InvalidReference:
    child: TransactionRef
    parent: TransactionRef
    reason: str


@dataclass(frozen=True)
class TransactionDAG:
    nodes: tuple[TransactionNode, ...]
    edges: tuple[TransactionEdge, ...]
    missing_parents: tuple[MissingParent, ...]
    invalid_references: tuple[InvalidReference, ...]
    conflicting_transactions: tuple[TransactionRef, ...]
    cycle_nodes: tuple[TransactionRef, ...]
    topological_order: tuple[TransactionRef, ...]

    @property
    def is_acyclic(self) -> bool:
        return not self.cycle_nodes

    @property
    def complete(self) -> bool:
        return not (
            self.missing_parents
            or self.invalid_references
            or self.conflicting_transactions
            or self.cycle_nodes
        )


def build_transaction_dag(records: Iterable[ObservedTransaction]) -> TransactionDAG:
    """Build parent→spend dependencies from explicit same-chain references only."""
    by_observation: dict[str, ObservedTransaction] = {}
    by_ref: dict[TransactionRef, list[ObservedTransaction]] = defaultdict(list)

    for record in records:
        previous = by_observation.get(record.observation_id)
        if previous is not None:
            if previous != record:
                raise ValueError(f"observation id reused with different transaction data: {record.observation_id}")
            continue
        by_observation[record.observation_id] = record
        by_ref[record.ref].append(record)

    refs = tuple(sorted(by_ref))
    nodes = tuple(
        TransactionNode(
            ref=ref,
            observation_ids=tuple(sorted(row.observation_id for row in by_ref[ref])),
            record_digests=tuple(sorted({row.record_digest for row in by_ref[ref]})),
        )
        for ref in refs
    )

    edge_evidence: dict[tuple[TransactionRef, TransactionRef], set[str]] = defaultdict(set)
    missing: set[MissingParent] = set()
    invalid: set[InvalidReference] = set()
    known = set(refs)

    for row in by_observation.values():
        for parent in row.parent_refs:
            if parent.chain != row.ref.chain:
                invalid.add(InvalidReference(row.ref, parent, "cross_chain_dependency_not_admissible"))
                continue
            if parent.network != row.ref.network:
                invalid.add(InvalidReference(row.ref, parent, "cross_network_dependency_not_admissible"))
                continue
            if parent not in known:
                missing.add(MissingParent(row.ref, parent))
                continue
            edge_evidence[(parent, row.ref)].add(row.observation_id)

    edges = tuple(
        TransactionEdge(parent, child, tuple(sorted(evidence)))
        for (parent, child), evidence in sorted(edge_evidence.items())
    )

    outgoing: dict[TransactionRef, set[TransactionRef]] = {ref: set() for ref in refs}
    indegree: dict[TransactionRef, int] = {ref: 0 for ref in refs}
    for edge in edges:
        if edge.child not in outgoing[edge.parent]:
            outgoing[edge.parent].add(edge.child)
            indegree[edge.child] += 1

    ready = sorted(ref for ref, degree in indegree.items() if degree == 0)
    ordered: list[TransactionRef] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(outgoing[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    cycles = tuple(sorted(ref for ref, degree in indegree.items() if degree > 0))
    conflicts = tuple(sorted(node.ref for node in nodes if node.conflicting))
    return TransactionDAG(
        nodes=nodes,
        edges=edges,
        missing_parents=tuple(sorted(missing)),
        invalid_references=tuple(sorted(invalid)),
        conflicting_transactions=conflicts,
        cycle_nodes=cycles,
        topological_order=tuple(ordered),
    )
