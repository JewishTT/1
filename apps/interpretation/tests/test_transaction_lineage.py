from __future__ import annotations

import pytest

from transaction_lineage import (
    ObservedTransaction,
    TransactionRef,
    build_transaction_dag,
)


def txid(char: str) -> str:
    return char * 64


def digest(char: str) -> str:
    return char * 64


def ref(chain: str, tx: str, network: str = "mainnet") -> TransactionRef:
    value = f"0x{txid(tx)}" if chain == "ethereum" else txid(tx)
    return TransactionRef(chain=chain, network=network, txid=value)  # type: ignore[arg-type]


def observed(
    current: TransactionRef,
    observation: str,
    record_hash: str,
    *parents: TransactionRef,
) -> ObservedTransaction:
    return ObservedTransaction(current, observation, digest(record_hash), tuple(parents))


def test_bitcoin_input_reference_creates_parent_to_spend_edge() -> None:
    coinbase = ref("bitcoin", "a")
    spend = ref("bitcoin", "b")
    dag = build_transaction_dag([
        observed(spend, "obs-spend", "1", coinbase),
        observed(coinbase, "obs-coinbase", "2"),
    ])
    assert len(dag.nodes) == 2
    assert len(dag.edges) == 1
    assert dag.edges[0].parent == coinbase
    assert dag.edges[0].child == spend
    assert dag.is_acyclic
    assert dag.complete
    assert dag.topological_order == (coinbase, spend)


def test_same_transaction_observed_twice_keeps_both_observation_ids() -> None:
    parent = ref("bitcoin", "a")
    spend = ref("bitcoin", "b")
    dag = build_transaction_dag([
        observed(parent, "parent-capture-1", "1"),
        observed(parent, "parent-capture-2", "1"),
        observed(spend, "spend-capture", "2", parent),
    ])
    assert len(dag.nodes) == 2
    assert dag.nodes[0].observation_ids == ("parent-capture-1", "parent-capture-2")
    assert len(dag.edges) == 1
    assert dag.edges[0].observation_ids == ("spend-capture",)


def test_missing_parent_is_reported_not_fabricated() -> None:
    missing = ref("bitcoin", "a")
    child = ref("bitcoin", "b")
    dag = build_transaction_dag([observed(child, "obs-child", "1", missing)])
    assert dag.edges == ()
    assert len(dag.missing_parents) == 1
    assert dag.missing_parents[0].parent == missing
    assert not dag.complete


def test_cross_chain_reference_is_rejected_without_joining_graphs() -> None:
    evm_parent = ref("ethereum", "a")
    btc_child = ref("bitcoin", "b")
    dag = build_transaction_dag([
        observed(evm_parent, "obs-eth", "1"),
        observed(btc_child, "obs-btc", "2", evm_parent),
    ])
    assert dag.edges == ()
    assert dag.invalid_references[0].reason == "cross_chain_dependency_not_admissible"
    assert not dag.complete


def test_conflicting_raw_digests_are_preserved_as_a_quality_condition() -> None:
    transaction = ref("bitcoin", "a")
    dag = build_transaction_dag([
        observed(transaction, "obs-1", "1"),
        observed(transaction, "obs-2", "2"),
    ])
    assert dag.conflicting_transactions == (transaction,)
    assert len(dag.nodes[0].record_digests) == 2
    assert not dag.complete


def test_cycle_is_reported_and_not_hidden_by_topological_sort() -> None:
    first = ref("bitcoin", "a")
    second = ref("bitcoin", "b")
    dag = build_transaction_dag([
        observed(first, "obs-a", "1", second),
        observed(second, "obs-b", "2", first),
    ])
    assert not dag.is_acyclic
    assert set(dag.cycle_nodes) == {first, second}
    assert dag.topological_order == ()


@pytest.mark.parametrize("chain", ["ethereum", "tron"])
def test_account_chain_feed_does_not_infer_edges_from_order_or_amount(chain: str) -> None:
    first = ref(chain, "a")  # type: ignore[arg-type]
    second = ref(chain, "b")  # type: ignore[arg-type]
    dag = build_transaction_dag([
        observed(first, "obs-first", "1"),
        observed(second, "obs-second", "2"),
    ])
    assert dag.edges == ()
    assert dag.is_acyclic
    assert dag.complete


def test_network_is_part_of_transaction_identity_and_dependency_scope() -> None:
    parent = ref("bitcoin", "a", "mainnet")
    child = ref("bitcoin", "b", "testnet")
    dag = build_transaction_dag([
        observed(parent, "obs-parent", "1"),
        observed(child, "obs-child", "2", parent),
    ])
    assert dag.edges == ()
    assert dag.invalid_references[0].reason == "cross_network_dependency_not_admissible"


def test_transaction_refs_require_canonical_chain_hashes() -> None:
    with pytest.raises(ValueError, match="invalid bitcoin"):
        TransactionRef(chain="bitcoin", network="mainnet", txid="not-a-hash")  # type: ignore[arg-type]
