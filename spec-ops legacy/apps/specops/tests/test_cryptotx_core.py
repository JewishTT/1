"""Core contract tests for the crypto transaction fabric.

These are the invariants the rest of the department relies on: a branched plan
validates as a DAG, a fallback edge is tied to failure, the vault round-trips a
key without writing it in clear, approval tokens are digest-bound, and the
ledger survives a process boundary.
"""

from __future__ import annotations

import time

import pytest
from specops.cryptotx import hd
from specops.cryptotx.approvals import mint_approval_token, verify_approval_token
from specops.cryptotx.errors import ApprovalRequired, PlanError, VaultError
from specops.cryptotx.models import Chain, EdgeWhen, Network, NodeKind, PlanState
from specops.cryptotx.planner import PlanBuilder, swap_with_fallback
from specops.cryptotx.store import Store
from specops.cryptotx.vault import create_vault, unlock_vault


def test_branched_plan_layers_and_digest(tmp_path):
    builder = PlanBuilder(network=Network.TESTNET)
    builder.transfer(
        "fund",
        wallet_id="w-1",
        chain=Chain.ETHEREUM,
        asset="ETH",
        amount="0.01",
        destination="0x0000000000000000000000000000000000000001",
    )
    builder.swap(
        "primary",
        wallet_id="w-1",
        chain=Chain.ETHEREUM,
        from_asset="ETH",
        amount="0.01",
        to_chain=Chain.BITCOIN,
        to_asset="BTC",
        destination="tb1qexample",
        after="fund",
    )
    builder.swap(
        "fallback",
        wallet_id="w-1",
        chain=Chain.ETHEREUM,
        from_asset="ETH",
        amount="0.01",
        to_chain=Chain.BITCOIN,
        to_asset="BTC",
        destination="tb1qexample",
        after="primary",
        when=EdgeWhen.FAILURE,
    )
    tree = builder.build(name="fund then swap")
    assert tree.state is PlanState.VALIDATED
    assert tree.topological_layers() == [["fund"], ["primary"], ["fallback"]]
    assert tree.node_map["primary"].kind is NodeKind.SWAP
    assert [edge.when for edge in tree.edges] == [
        EdgeWhen.SUCCESS,
        EdgeWhen.FAILURE,
    ]
    assert tree.digest() == builder.build(name="fund then swap", plan_id=tree.plan_id).digest()


def test_cycle_is_refused():
    builder = PlanBuilder()
    builder.transfer(
        "a",
        wallet_id="w",
        chain=Chain.ETHEREUM,
        asset="ETH",
        amount="1",
        destination="0x0000000000000000000000000000000000000001",
    )
    builder.transfer(
        "b",
        wallet_id="w",
        chain=Chain.ETHEREUM,
        asset="ETH",
        amount="1",
        destination="0x0000000000000000000000000000000000000002",
    )
    builder.link("a", "b").link("b", "a")
    with pytest.raises(PlanError):
        builder.build(name="cycle")


def test_swap_fallback_template_has_failure_edge():
    tree = swap_with_fallback(
        name="bridge",
        wallet_id="w",
        chain=Chain.ETHEREUM,
        from_asset="ETH",
        amount="0.1",
        to_chain=Chain.BITCOIN,
        to_asset="BTC",
        destination="tb1qexample",
        providers=["thorchain", "uniswap"],
    )
    fallback = tree.node_map["swap-fallback"]
    assert fallback.params["providers"] == ["uniswap", "thorchain"]
    assert tree.edges[0].when is EdgeWhen.FAILURE


def test_vault_round_trip_and_derived_address(tmp_path, monkeypatch):
    monkeypatch.setenv("CRYPTOTX_SCRYPT_N", "4096")
    path = tmp_path / "vault.json"
    vault = create_vault(path, "correct horse battery", words=12)
    wallet = vault.add_wallet(Chain.ETHEREUM, Network.TESTNET, "ops")
    material = vault.private_key(wallet.wallet_id)
    assert material.address == wallet.address
    assert wallet.derivation_path.startswith("m/44h/60h/0h/0/")
    raw = path.read_text(encoding="utf-8")
    assert "mnemonic" not in raw
    assert material.private_key.hex() not in raw

    reopened = unlock_vault(path, "correct horse battery")
    assert reopened.wallet(wallet.wallet_id).address == wallet.address
    with pytest.raises(VaultError):
        unlock_vault(path, "wrong password")


def test_approval_token_is_digest_bound_and_expires(monkeypatch):
    secret = "s" * 32
    digest = "a" * 64
    token = mint_approval_token(digest, secret, ttl_s=60)
    assert verify_approval_token(digest, token, secret) > int(time.time())
    with pytest.raises(ApprovalRequired):
        verify_approval_token("b" * 64, token, secret)
    with pytest.raises(ApprovalRequired):
        verify_approval_token(digest, None, secret)
    with pytest.raises(ApprovalRequired):
        verify_approval_token(digest, token, None)

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 3600)
    with pytest.raises(ApprovalRequired):
        verify_approval_token(digest, token, secret)


def test_store_round_trip(tmp_path):
    from specops.cryptotx.models import ExecutionResult, NodeResult, NodeState

    store = Store(tmp_path / "state.sqlite3")
    tree = PlanBuilder(network=Network.TESTNET).transfer(
        "pay",
        wallet_id="w",
        chain=Chain.ETHEREUM,
        asset="ETH",
        amount="0.01",
        destination="0x0000000000000000000000000000000000000001",
    ).build(name="pay")
    store.save_plan(tree)
    loaded = store.get_plan(tree.plan_id)
    assert loaded is not None and loaded.digest() == tree.digest()

    run = ExecutionResult(
        run_id="run-test",
        plan_id=tree.plan_id,
        plan_digest=tree.digest(),
        dry_run=True,
        state=PlanState.RUNNING,
    )
    store.start_run(run)
    node = NodeResult(node_id="pay", state=NodeState.SUCCEEDED, tx_hash="0xabc")
    store.save_node_result(run.run_id, node)
    run.state = PlanState.COMPLETED
    run.node_results["pay"] = node
    store.finish_run(run)
    fetched = store.get_run(run.run_id)
    assert fetched is not None
    assert fetched["state"] == "completed"
    assert fetched["node_results"]["pay"]["tx_hash"] == "0xabc"
    assert store.list_runs(plan_id=tree.plan_id)[0]["run_id"] == "run-test"
    store.audit("tester", "checked", plan_id=tree.plan_id)
    assert store.audit_events()[0]["action"] == "checked"
    assert store.stats()["runs"] == 1


def test_known_bitcoin_derivation_paths():
    seed = hd.seed_from_mnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon about"
    )
    key = hd.derive_key(seed, Chain.BITCOIN, Network.TESTNET, 0)
    assert key.address.startswith("tb1")
    assert key.path == "m/84h/0h/0h/0/0"
    assert "private_key" not in repr(key)
    tron = hd.derive_key(seed, Chain.TRON, Network.TESTNET, 0)
    assert tron.address.startswith("T")
    assert tron.path == "m/44h/195h/0h/0/0"
