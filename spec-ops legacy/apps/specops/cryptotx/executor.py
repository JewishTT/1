"""Branch-aware transaction executor.

The executor walks the DAG layer by layer. A node runs when every incoming edge
is satisfied by the source node's terminal state; otherwise it is skipped and
its own outgoing edges are not taken. Independent roots run concurrently in the
same layer. That is the whole scheduler: no hidden state machine, no retries of
a broadcast that may already have landed.

Money-moving defaults are not negotiable here:

* ``dry_run`` builds and signs every transaction but never broadcasts.
* live execution needs ``CRYPTOTX_ALLOW_MAINNET=1`` for mainnet, an unlocked
  vault, and an HMAC token bound to the plan digest.
* every live node is checked against per-chain caps, a native gas reserve and
  the optional destination allowlist before signing.
* a token swap approval is prepared and confirmed automatically; the operator
  approves the swap intent, not each ERC20/TRC20 allowance.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from specops.cryptotx.approvals import verify_approval_token
from specops.cryptotx.chains.base import BroadcastReceipt, ChainAdapter
from specops.cryptotx.chains.registry import asset_for, make_adapter
from specops.cryptotx.config import CryptoTxConfig, get_config
from specops.cryptotx.errors import (
    ChainError,
    CryptoTxError,
    NodeFailed,
    PlanError,
    PolicyError,
    SwapError,
)
from specops.cryptotx.hd import DerivedKey
from specops.cryptotx.models import (
    Asset,
    Chain,
    EdgeWhen,
    ExecutionResult,
    Network,
    NodeKind,
    NodeResult,
    NodeState,
    PlanState,
    SwapInstruction,
    SwapQuote,
    TransactionTree,
    TxEdge,
    TxNode,
    now_iso,
)
from specops.cryptotx.store import Store, plan_state_from_results
from specops.cryptotx.swaps.base import SwapRequest
from specops.cryptotx.swaps.router import SwapRouter
from specops.cryptotx.vault import UnlockedVault, unlock_vault


def _edge_satisfied(edge: TxEdge, state: NodeState) -> bool:
    if edge.when is EdgeWhen.SUCCESS:
        return state is NodeState.SUCCEEDED
    if edge.when is EdgeWhen.FAILURE:
        return state is NodeState.FAILED
    return state in {NodeState.SUCCEEDED, NodeState.FAILED}


class Executor:
    def __init__(
        self,
        *,
        config: CryptoTxConfig | None = None,
        store: Store | None = None,
        vault: UnlockedVault | None = None,
        adapters: dict[Chain, ChainAdapter] | None = None,
        swap_router: SwapRouter | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.config = config or get_config()
        self.store = store or Store(self.config.state_path)
        self.vault = vault
        self._adapters = dict(adapters or {})
        self._owned: set[Chain] = set()
        self.swap_router = swap_router
        self.transport = transport
        self.sleep = sleep
        self.clock = clock

    def run(
        self,
        plan: TransactionTree,
        *,
        password: str | None = None,
        dry_run: bool | None = None,
        approval_token: str | None = None,
        actor: str = "operator",
        run_id: str | None = None,
    ) -> ExecutionResult:
        cfg = self.config
        plan.validate()
        if plan.network is Network.MAINNET and not cfg.allow_mainnet:
            raise PolicyError(
                "mainnet is disabled; set CRYPTOTX_ALLOW_MAINNET=1 to run this plan"
            )
        for node in plan.nodes:
            if node.network is not plan.network:
                raise PlanError(
                    f"node {node.node_id!r} is {node.network.value} but the plan is "
                    f"{plan.network.value}"
                )
            if not cfg.mainnet_permitted(node.network):
                raise PolicyError(f"node {node.node_id!r} targets disabled mainnet")
        digest = plan.digest()
        if dry_run is None:
            dry_run = cfg.dry_run_default
        if not dry_run:
            verify_approval_token(digest, approval_token, cfg.approval_secret)

        vault = self.vault
        if vault is None:
            if not password:
                raise PolicyError("the vault password is required to sign transactions")
            vault = unlock_vault(cfg.vault_path, password)

        if plan.state is PlanState.DRAFT:
            plan.state = PlanState.VALIDATED
        self.store.save_plan(plan)
        result = ExecutionResult(
            run_id=run_id or f"run-{uuid.uuid4().hex[:12]}",
            plan_id=plan.plan_id,
            plan_digest=digest,
            dry_run=dry_run,
            state=PlanState.RUNNING,
        )
        self.store.start_run(result)
        self.store.audit(
            actor,
            "run_started",
            plan_id=plan.plan_id,
            run_id=result.run_id,
            detail={"dry_run": dry_run, "network": plan.network.value},
        )
        if dry_run:
            result.notes.append(
                "dry-run: every transaction was prepared and signed locally but none "
                "was broadcast"
            )

        try:
            self._walk(plan, result, vault, dry_run)
            result.state = plan_state_from_results(list(result.node_results.values()))
            plan.state = result.state
            result.finished_at = now_iso()
            self.store.save_plan(plan)
            self.store.finish_run(result)
            self.store.audit(
                actor,
                "run_finished",
                plan_id=plan.plan_id,
                run_id=result.run_id,
                detail={"state": result.state.value, "dry_run": dry_run},
            )
            return result
        except Exception:
            result.state = PlanState.FAILED
            result.finished_at = now_iso()
            result.notes.append("run aborted before every node reached a terminal state")
            self.store.finish_run(result)
            plan.state = PlanState.FAILED
            self.store.save_plan(plan)
            self.store.audit(
                actor,
                "run_aborted",
                plan_id=plan.plan_id,
                run_id=result.run_id,
                detail={},
            )
            raise
        finally:
            for chain in self._owned:
                adapter = self._adapters.get(chain)
                close = getattr(adapter, "close", None)
                if close is not None:
                    close()
            self._owned.clear()
            if self.vault is None:
                self._adapters.clear()

    def _walk(
        self,
        plan: TransactionTree,
        result: ExecutionResult,
        vault: UnlockedVault,
        dry_run: bool,
    ) -> None:
        incoming: dict[str, list[TxEdge]] = {}
        for edge in plan.edges:
            incoming.setdefault(edge.target, []).append(edge)
        totals: dict[Chain, Decimal] = {}
        for layer in plan.topological_layers():
            for node_id in layer:
                node = plan.node_map[node_id]
                edges = incoming.get(node_id, [])
                if edges and not self._branch_ready(edges, result.node_results):
                    skipped = NodeResult(
                        node_id=node_id,
                        state=NodeState.SKIPPED,
                        finished_at=now_iso(),
                        detail={"reason": "branch not taken"},
                    )
                    result.node_results[node_id] = skipped
                    self.store.save_node_result(result.run_id, skipped)
                    continue
                node_result = self._run_node(
                    plan, node, vault, result.node_results, totals, dry_run
                )
                result.node_results[node_id] = node_result
                self.store.save_node_result(result.run_id, node_result)
                self.store.audit(
                    "executor",
                    f"node_{node_result.state.value}",
                    plan_id=plan.plan_id,
                    run_id=result.run_id,
                    node_id=node_id,
                    detail={
                        "tx_hash": node_result.tx_hash,
                        "error": node_result.error,
                        "dry_run": dry_run,
                    },
                )

    @staticmethod
    def _branch_ready(
        edges: list[TxEdge], results: dict[str, NodeResult]
    ) -> bool:
        for edge in edges:
            parent = results.get(edge.source)
            if parent is None or not parent.state.terminal:
                return False
            if not _edge_satisfied(edge, parent.state):
                return False
        return True

    def _run_node(
        self,
        plan: TransactionTree,
        node: TxNode,
        vault: UnlockedVault,
        results: dict[str, NodeResult],
        totals: dict[Chain, Decimal],
        dry_run: bool,
    ) -> NodeResult:
        started = NodeResult(node_id=node.node_id, state=NodeState.RUNNING)
        try:
            output = self._execute_node(plan, node, vault, results, totals, dry_run)
            started.state = NodeState.SUCCEEDED
            started.tx_hash = output.pop("tx_hash", None)
            started.provider = output.pop("provider", None)
            started.prepared = output.pop("prepared", None)
            started.signed = output.pop("signed", None)
            started.receipt = output.pop("receipt", None)
            started.detail = output.pop("detail", {})
            started.detail.update(output)
        except CryptoTxError as exc:
            started.state = NodeState.FAILED
            started.error = exc.reason
            started.detail = {"error_code": exc.code, **exc.context}
        except Exception as exc:  # noqa: BLE001 - one node must not abort the tree
            started.state = NodeState.FAILED
            started.error = f"{type(exc).__name__}: {exc}"
            started.detail = {"error_code": "UnhandledError"}
        started.finished_at = now_iso()
        return started

    def _execute_node(
        self,
        plan: TransactionTree,
        node: TxNode,
        vault: UnlockedVault,
        results: dict[str, NodeResult],
        totals: dict[Chain, Decimal],
        dry_run: bool,
    ) -> dict[str, Any]:
        if node.kind is NodeKind.NOOP:
            return {"detail": {"note": "no-op"}}
        if node.kind is NodeKind.WAIT:
            return self._wait(plan, node, results, dry_run)
        material = self._material(node, vault)
        adapter = self._adapter(node.chain, node.network)
        if node.kind is NodeKind.TRANSFER:
            return self._transfer(adapter, node, material, totals, dry_run)
        if node.kind is NodeKind.APPROVE:
            return self._approve(adapter, node, material, dry_run)
        if node.kind is NodeKind.SWAP:
            return self._swap(adapter, node, material, totals, dry_run)
        raise PlanError(f"unsupported node kind {node.kind.value!r}")

    def _adapter(self, chain: Chain, network: Network) -> ChainAdapter:
        adapter = self._adapters.get(chain)
        if adapter is not None:
            if adapter.network is not network:
                raise PlanError("injected adapter targets a different network")
            return adapter
        adapter = make_adapter(
            chain, network, config=self.config, transport=self.transport
        )
        self._adapters[chain] = adapter
        self._owned.add(chain)
        return adapter

    def _material(self, node: TxNode, vault: UnlockedVault) -> DerivedKey:
        if not node.wallet_id:
            raise PolicyError(f"node {node.node_id!r} has no wallet_id")
        wallet = vault.wallet(node.wallet_id)
        if wallet.chain is not node.chain or wallet.network is not node.network:
            raise PolicyError(
                f"wallet {wallet.wallet_id!r} is {wallet.chain.value}/"
                f"{wallet.network.value}, node needs {node.chain.value}/"
                f"{node.network.value}"
            )
        return vault.private_key(node.wallet_id)

    def _asset(self, chain: Chain, network: Network, symbol: str,
               params: dict[str, Any]) -> Asset:
        try:
            return asset_for(chain, network, symbol, params)
        except ValueError as exc:
            raise PlanError(f"unknown asset {symbol!r} on {chain.value}: {exc}") from exc

    def _check_destination(self, destination: str | None) -> None:
        if not destination:
            return
        allowed = self.config.allowed_destinations
        if not allowed:
            if self.config.require_allowlist:
                raise PolicyError("destination allowlist is required but empty")
            return
        if destination.lower() not in allowed:
            raise PolicyError(f"destination {destination!r} is not allowlisted")

    def _check_amount(
        self, node: TxNode, asset: Asset, amount: Decimal,
        totals: dict[Chain, Decimal],
    ) -> None:
        if amount <= 0:
            raise PolicyError(f"node {node.node_id!r} has a non-positive amount")
        if not asset.native:
            return
        limit = self.config.max_tx_native[node.chain]
        if amount > limit:
            raise PolicyError(
                f"{amount} {asset.symbol} exceeds the per-transaction cap {limit}"
            )
        proposed = totals.get(node.chain, Decimal(0)) + amount
        total_limit = self.config.max_total_native[node.chain]
        if proposed > total_limit:
            raise PolicyError(
                f"plan native total on {node.chain.value} would reach {proposed}, "
                f"cap is {total_limit}"
            )
        totals[node.chain] = proposed

    def _check_funds(
        self, adapter: ChainAdapter, material: DerivedKey, asset: Asset,
        amount: Decimal, fee: Decimal,
    ) -> None:
        native = adapter.native_asset()
        reserve = self.config.min_gas_reserve[asset.chain]
        if asset.native:
            balance = adapter.get_balance(material.address, native)
            needed = amount + fee + reserve
            if balance < needed:
                raise PolicyError(
                    f"insufficient {native.symbol}: have {balance}, need {needed} "
                    f"(amount {amount}, fee {fee}, reserve {reserve})"
                )
            return
        balance = adapter.get_balance(material.address, asset)
        if balance < amount:
            raise PolicyError(
                f"insufficient {asset.symbol}: have {balance}, need {amount}"
            )
        native_balance = adapter.get_balance(material.address, native)
        if native_balance < fee + reserve:
            raise PolicyError(
                f"insufficient {native.symbol} for fees: have {native_balance}, "
                f"need {fee + reserve} (fee {fee}, reserve {reserve})"
            )

    def _sign_and_send(
        self, adapter: ChainAdapter, material: DerivedKey,
        prepared, dry_run: bool,
    ) -> dict[str, Any]:
        signed = adapter.sign(prepared, material)
        output: dict[str, Any] = {
            "tx_hash": signed.tx_hash,
            "prepared": prepared.to_dict(),
            "signed": signed.to_dict(),
            "detail": {
                "dry_run": dry_run,
                "broadcast": not dry_run,
                "fee": str(prepared.fee),
            },
        }
        if dry_run:
            return output
        receipt: BroadcastReceipt = adapter.broadcast(signed)
        output["receipt"] = receipt.to_dict()
        output["tx_hash"] = receipt.tx_hash
        return output

    def _transfer(
        self, adapter: ChainAdapter, node: TxNode, material: DerivedKey,
        totals: dict[Chain, Decimal], dry_run: bool,
    ) -> dict[str, Any]:
        if not node.destination:
            raise PlanError(f"transfer node {node.node_id!r} has no destination")
        asset = self._asset(node.chain, node.network, node.asset, node.params)
        destination = adapter.validate_address(node.destination)
        self._check_destination(destination)
        amount = node.decimal_amount()
        self._check_amount(node, asset, amount, totals)
        prepared = adapter.prepare_transfer(
            material,
            destination,
            asset,
            amount,
            memo=str(node.params.get("memo", "")),
            fee_rate=(Decimal(str(node.params["fee_rate"]))
                      if node.params.get("fee_rate") is not None else None),
        )
        if not dry_run:
            self._check_funds(adapter, material, asset, amount, prepared.fee)
        return self._sign_and_send(adapter, material, prepared, dry_run)

    def _approve(
        self, adapter: ChainAdapter, node: TxNode, material: DerivedKey,
        dry_run: bool,
    ) -> dict[str, Any]:
        asset = self._asset(node.chain, node.network, node.asset, node.params)
        spender = adapter.validate_address(str(node.params["spender"]))
        amount = node.decimal_amount()
        prepare = getattr(adapter, "prepare_approve", None)
        if prepare is None:
            raise ChainError(f"{node.chain.value} adapter cannot approve tokens")
        prepared = prepare(
            material, asset, spender, amount=amount if amount > 0 else None
        )
        if not dry_run:
            self._check_funds(
                adapter, material, asset, Decimal(0), prepared.fee
            )
        return self._sign_and_send(adapter, material, prepared, dry_run)

    def _swap(
        self, adapter: ChainAdapter, node: TxNode, material: DerivedKey,
        totals: dict[Chain, Decimal], dry_run: bool,
    ) -> dict[str, Any]:
        params = node.params
        try:
            to_chain = Chain(str(params["to_chain"]))
        except (KeyError, ValueError) as exc:
            raise PlanError(f"swap node {node.node_id!r} has an invalid to_chain") from exc
        from_asset = self._asset(node.chain, node.network, node.asset, params)
        to_asset = self._asset(
            to_chain, node.network, str(params["to_asset"]), params
        )
        destination = node.destination or ""
        destination = self._adapter(to_chain, node.network).validate_address(destination)
        self._check_destination(destination)
        amount = node.decimal_amount()
        self._check_amount(node, from_asset, amount, totals)
        providers = tuple(str(item) for item in (params.get("providers") or ()))
        minimum = params.get("min_amount_out")
        request = SwapRequest(
            from_chain=node.chain,
            to_chain=to_chain,
            network=node.network,
            from_asset=from_asset,
            to_asset=to_asset,
            amount=amount,
            from_address=material.address,
            to_address=destination,
            slippage_bps=int(params.get("slippage_bps", self.config.swap_slippage_bps)),
            min_amount_out=Decimal(str(minimum)) if minimum is not None else None,
            providers=providers,
        )
        router = self.swap_router or SwapRouter(
            self.config, transport=self.transport
        )
        quote, attempts = router.best(request)
        self._ensure_fresh(quote)
        instruction = quote.instruction
        if instruction is None:
            raise SwapError("swap quote has no executable instruction")
        detail: dict[str, Any] = {
            "quote": quote.to_dict(include_raw=False),
            "attempts": [
                {"provider": item.provider, "ok": item.ok, "error": item.error}
                for item in attempts
            ],
        }
        if instruction.approval_spender:
            if from_asset.native:
                raise SwapError("a native asset cannot need an allowance")
            approval = self._run_approval(
                adapter, node, material, from_asset, instruction, dry_run
            )
            detail["approval"] = approval
            detail["approval_tx_hash"] = approval.pop("tx_hash", None)
            self._ensure_fresh(quote)
        prepared = self._prepare_swap(adapter, material, instruction, from_asset)
        if not dry_run:
            self._check_funds(adapter, material, from_asset, amount, prepared.fee)
        output = self._sign_and_send(adapter, material, prepared, dry_run)
        output["provider"] = quote.provider
        output["detail"].update(detail)
        return output

    @staticmethod
    def _ensure_fresh(quote: SwapQuote) -> None:
        if not quote.expires_at:
            return
        try:
            moment = datetime.fromisoformat(quote.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SwapError("swap quote has an invalid expiry") from exc
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        if moment <= datetime.now(UTC):
            raise SwapError("swap quote expired before execution")

    def _prepare_swap(
        self, adapter: ChainAdapter, material: DerivedKey,
        instruction: SwapInstruction, from_asset: Asset,
    ):
        if instruction.kind == "deposit":
            return adapter.prepare_transfer(
                material,
                instruction.to,
                from_asset,
                instruction.amount,
                memo=instruction.memo,
            )
        return adapter.prepare_call(material, instruction, asset=from_asset)

    def _run_approval(
        self, adapter: ChainAdapter, node: TxNode, material: DerivedKey,
        asset: Asset, instruction: SwapInstruction, dry_run: bool,
    ) -> dict[str, Any]:
        prepare = getattr(adapter, "prepare_approve", None)
        if prepare is None:
            raise ChainError(f"{node.chain.value} adapter cannot approve tokens")
        amount = (
            Decimal(instruction.approval_amount)
            if instruction.approval_amount else None
        )
        prepared = prepare(
            material, asset, instruction.approval_spender, amount=amount
        )
        if not dry_run:
            self._check_funds(
                adapter, material, asset, Decimal(0), prepared.fee
            )
        output = self._sign_and_send(adapter, material, prepared, dry_run)
        if not dry_run:
            self._await_confirmations(
                adapter, output["tx_hash"], 1, min(node.timeout_s, 180)
            )
        return output

    def _wait(
        self, plan: TransactionTree, node: TxNode, results: dict[str, NodeResult],
        dry_run: bool,
    ) -> dict[str, Any]:
        reference = str(node.params.get("tx_node") or "")
        if not reference:
            raise PlanError(f"wait node {node.node_id!r} has no tx_node")
        source_node = plan.node_map.get(reference)
        if source_node is None:
            raise PlanError(f"wait node {node.node_id!r} references unknown node")
        parent = results.get(reference)
        if parent is None or parent.state is not NodeState.SUCCEEDED:
            raise NodeFailed(f"{reference!r} did not succeed; nothing to wait for")
        if not parent.tx_hash:
            raise NodeFailed(f"{reference!r} has no transaction hash")
        required = int(node.params.get("confirmations", 1))
        if dry_run:
            return {
                "detail": {
                    "note": "dry-run: confirmations are not awaited",
                    "tx_node": reference,
                    "confirmations": required,
                }
            }
        adapter = self._adapter(source_node.chain, node.network)
        self._await_confirmations(
            adapter,
            parent.tx_hash,
            required,
            node.timeout_s,
            float(node.params.get("poll_interval_s", 2.0)),
        )
        return {
            "tx_hash": parent.tx_hash,
            "detail": {"confirmations": required, "tx_node": reference},
        }

    def _await_confirmations(
        self, adapter: ChainAdapter, tx_hash: str, required: int, timeout_s: float,
        poll_interval_s: float = 2.0,
    ) -> None:
        deadline = self.clock() + max(0.0, timeout_s)
        last_error: str | None = None
        while self.clock() < deadline:
            try:
                if adapter.confirmations(tx_hash) >= required:
                    return
            except Exception as exc:  # noqa: BLE001 - node may not have indexed it yet
                last_error = f"{type(exc).__name__}: {exc}"
            self.sleep(min(poll_interval_s, max(0.0, deadline - self.clock())))
        suffix = f" (last error: {last_error})" if last_error else ""
        raise NodeFailed(
            f"transaction {tx_hash} did not reach {required} confirmation(s) in "
            f"{timeout_s:g}s{suffix}"
        )
