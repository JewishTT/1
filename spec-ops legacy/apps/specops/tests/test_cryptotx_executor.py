"""Executor behavior: branches, dry-run signing, live approval and policy.

The adapters here are fakes, not mocks of the RPC wire: they implement the same
contract the real chain adapters do, so the scheduler, vault lookup, policy gate
and signing path are exercised together without a network.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from eth_utils import is_address, to_checksum_address
from specops.cryptotx.approvals import mint_approval_token
from specops.cryptotx.chains.base import BroadcastReceipt, ChainAdapter
from specops.cryptotx.config import clear_config_cache, get_config
from specops.cryptotx.errors import ApprovalRequired, ChainError, SwapUnavailable
from specops.cryptotx.executor import Executor
from specops.cryptotx.models import (
    Asset,
    Chain,
    Network,
    NodeState,
    PlanState,
    PreparedTransaction,
    SignedTransaction,
    SwapInstruction,
    SwapQuote,
)
from specops.cryptotx.planner import PlanBuilder, swap_with_fallback
from specops.cryptotx.store import Store
from specops.cryptotx.swaps.base import SwapRequest
from specops.cryptotx.swaps.router import SwapAttempt
from specops.cryptotx.vault import create_vault


@pytest.fixture(autouse=True)
def _clear_config():
    clear_config_cache()
    yield
    clear_config_cache()


def _config(tmp_path, **overrides):
    base = get_config()
    values = {
        "data_dir": tmp_path,
        "vault_path": tmp_path / "vault.json",
        "state_path": tmp_path / "state.sqlite3",
        "allow_mainnet": True,
        "dry_run_default": True,
        "approval_secret": "s" * 32,
        "request_timeout_s": 5.0,
        "max_retries": 0,
    }
    values.update(overrides)
    return replace(base, **values)


class FakeAdapter(ChainAdapter):
    chain = Chain.ETHEREUM

    def __init__(self, network: Network = Network.TESTNET) -> None:
        self.network = network
        self.broadcasts: list[SignedTransaction] = []
        self.balances = {"ETH": Decimal("100"), "USDC": Decimal("100")}
        self.counter = 0
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def native_asset(self) -> Asset:
        return Asset(Chain.ETHEREUM, "ETH", 18)

    def validate_address(self, address: str) -> str:
        if not is_address(address):
            raise ChainError("bad address")
        return to_checksum_address(address)

    def get_balance(self, address: str, asset: Asset) -> Decimal:
        return self.balances.get(asset.symbol, Decimal(0))

    def _prepared(self, asset: Asset, amount: Decimal, description: str):
        return PreparedTransaction(
            chain=Chain.ETHEREUM,
            network=self.network,
            from_address="0x0000000000000000000000000000000000000001",
            to_address="0x0000000000000000000000000000000000000002",
            asset=asset,
            amount=amount,
            fee=Decimal("0.0001"),
            payload={"kind": description},
            description=description,
        )

    def prepare_transfer(self, material, to_address, asset, amount, *, memo="",
                         fee_rate=None, **kwargs):
        return self._prepared(asset, amount, "transfer")

    def prepare_approve(self, material, asset, spender, *, amount=None):
        return self._prepared(asset, Decimal(0), "approve")

    def prepare_call(self, material, instruction, *, asset):
        return self._prepared(asset, instruction.amount, "call")

    def sign(self, prepared, material):
        self.counter += 1
        return SignedTransaction(
            chain=Chain.ETHEREUM,
            network=self.network,
            tx_hash=f"0x{self.counter:064x}",
            raw="0xsigned",
            prepared=prepared,
        )

    def broadcast(self, signed):
        self.broadcasts.append(signed)
        return BroadcastReceipt(signed.tx_hash, True, {"fake": True})

    def confirmations(self, tx_hash):
        return 1


class FakeRouter:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls = 0

    def best(self, request: SwapRequest):
        self.calls += 1
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, SwapQuote)
        return item, [SwapAttempt("fake", quote=item)]


def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("CRYPTOTX_SCRYPT_N", "4096")
    vault = create_vault(tmp_path / "vault.json", "correct horse battery")
    wallet = vault.add_wallet(Chain.ETHEREUM, Network.TESTNET, "ops")
    return vault, wallet


def _quote(wallet, *, token: bool) -> SwapQuote:
    router = "0x0000000000000000000000000000000000000002"
    if token:
        instruction = SwapInstruction(
            kind="evm_call",
            chain=Chain.ETHEREUM,
            to=router,
            asset="USDC",
            amount=Decimal("10"),
            calldata="0x1234",
            approval_spender=router,
            approval_asset="USDC",
            approval_amount="10",
        )
    else:
        instruction = SwapInstruction(
            kind="evm_call",
            chain=Chain.ETHEREUM,
            to=router,
            asset="ETH",
            amount=Decimal("0.01"),
            value=Decimal("0.01"),
            calldata="0x5678",
        )
    return SwapQuote(
        provider="fake",
        from_chain=Chain.ETHEREUM,
        to_chain=Chain.ETHEREUM,
        from_asset="USDC" if token else "ETH",
        to_asset="ETH" if token else "USDC",
        amount_in=Decimal("10") if token else Decimal("0.01"),
        expected_amount_out=Decimal("0.005"),
        min_amount_out=Decimal("0.0049"),
        from_address=wallet.address,
        to_address=wallet.address,
        route="fake route",
        instruction=instruction,
    )


def test_dry_run_signs_and_never_broadcasts(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path)
    adapter = FakeAdapter()
    plan = (
        PlanBuilder()
        .transfer(
            "fund",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            asset="ETH",
            amount="0.01",
            destination=wallet.address,
        )
        .transfer(
            "second",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            asset="ETH",
            amount="0.02",
            destination=wallet.address,
            after="fund",
        )
        .build(name="two legs")
    )
    result = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter},
    ).run(plan, dry_run=True)

    assert result.state is PlanState.COMPLETED
    assert set(result.node_results) == {"fund", "second"}
    assert all(node.state is NodeState.SUCCEEDED for node in result.node_results.values())
    assert adapter.broadcasts == []
    assert result.node_results["fund"].signed is not None
    assert result.node_results["fund"].detail["broadcast"] is False


def test_live_swap_requires_approval_token(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path)
    adapter = FakeAdapter()
    plan = (
        PlanBuilder()
        .swap(
            "swap",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            from_asset="ETH",
            amount="0.01",
            to_chain=Chain.ETHEREUM,
            to_asset="USDC",
            destination=wallet.address,
        )
        .build(name="swap")
    )
    executor = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter},
        swap_router=FakeRouter([_quote(wallet, token=False)]),
    )
    with pytest.raises(ApprovalRequired):
        executor.run(plan, dry_run=False)
    assert adapter.broadcasts == []

    token = mint_approval_token(plan.digest(), cfg.approval_secret)
    result = executor.run(plan, dry_run=False, approval_token=token)
    assert result.state is PlanState.COMPLETED
    assert len(adapter.broadcasts) == 1


def test_live_token_swap_approves_then_swaps(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path)
    adapter = FakeAdapter()
    plan = (
        PlanBuilder()
        .swap(
            "swap",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            from_asset="USDC",
            amount="10",
            to_chain=Chain.ETHEREUM,
            to_asset="ETH",
            destination=wallet.address,
        )
        .build(name="usdc to eth")
    )
    token = mint_approval_token(plan.digest(), cfg.approval_secret)
    result = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter},
        swap_router=FakeRouter([_quote(wallet, token=True)]),
    ).run(plan, dry_run=False, approval_token=token)

    node = result.node_results["swap"]
    assert node.state is NodeState.SUCCEEDED
    assert len(adapter.broadcasts) == 2
    assert node.detail["approval_tx_hash"] == "0x" + f"{1:064x}"
    assert node.detail["quote"]["provider"] == "fake"
    stored = Store(cfg.state_path).get_run(result.run_id)
    assert stored is not None and stored["state"] == "completed"


def test_failure_branch_runs_fallback(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path)
    adapter = FakeAdapter()
    good = _quote(wallet, token=False)
    router = FakeRouter([SwapUnavailable("primary pool closed"), good])
    plan = swap_with_fallback(
        name="fallback",
        wallet_id=wallet.wallet_id,
        chain=Chain.ETHEREUM,
        from_asset="ETH",
        amount="0.01",
        to_chain=Chain.ETHEREUM,
        to_asset="USDC",
        destination=wallet.address,
    )
    result = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter}, swap_router=router,
    ).run(plan, dry_run=True)

    assert result.node_results["swap-primary"].state is NodeState.FAILED
    assert result.node_results["swap-fallback"].state is NodeState.SUCCEEDED
    assert result.state is PlanState.PARTIAL
    assert router.calls == 2


def test_allowlist_blocks_before_signing(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path, require_allowlist=True, allowed_destinations=frozenset())
    adapter = FakeAdapter()
    plan = (
        PlanBuilder()
        .transfer(
            "pay",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            asset="ETH",
            amount="0.01",
            destination=wallet.address,
        )
        .build(name="pay")
    )
    result = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter},
    ).run(plan, dry_run=True)
    node = result.node_results["pay"]
    assert node.state is NodeState.FAILED
    assert "allowlist" in (node.error or "")
    assert adapter.broadcasts == []


def test_expired_quote_is_never_signed(tmp_path, monkeypatch):
    vault, wallet = _vault(tmp_path, monkeypatch)
    cfg = _config(tmp_path)
    adapter = FakeAdapter()
    quote = replace(
        _quote(wallet, token=False),
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )
    plan = (
        PlanBuilder()
        .swap(
            "swap",
            wallet_id=wallet.wallet_id,
            chain=Chain.ETHEREUM,
            from_asset="ETH",
            amount="0.01",
            to_chain=Chain.ETHEREUM,
            to_asset="USDC",
            destination=wallet.address,
        )
        .build(name="expired quote")
    )
    result = Executor(
        config=cfg, store=Store(cfg.state_path), vault=vault,
        adapters={Chain.ETHEREUM: adapter},
        swap_router=FakeRouter([quote]),
    ).run(plan, dry_run=True)

    node = result.node_results["swap"]
    assert node.state is NodeState.FAILED
    assert "expired" in (node.error or "")
    assert adapter.broadcasts == []