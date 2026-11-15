"""Branched transaction-tree planner.

The planner is a small fluent builder over the DAG model. It deliberately does
not decide prices, approvals or routing; it records dependencies, branch
predicates and the intent of each node. Validation and execution belong to
``TransactionTree.validate`` and the executor.

Two templates cover the common treasury shapes:

``fan_out``
    one funding transfer, then independent distributions. A distribution edge
    can be ``success`` (pay only if the funding leg settled) or ``failure``
    (fallback path).

``swap_with_fallback``
    an approval, a primary swap, and a fallback swap reached only when the
    primary leg fails. This is the automated cross-chain case: THORChain and
    the EVM/SunSwap routers are tried in order, and settlement continues on
    whichever branch actually filled.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from specops.cryptotx.errors import PlanError
from specops.cryptotx.models import (
    Chain,
    EdgeWhen,
    Network,
    NodeKind,
    PlanState,
    TransactionTree,
    TxEdge,
    TxNode,
    now_iso,
)


def new_plan_id(prefix: str = "plan") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class PlanBuilder:
    network: Network = Network.TESTNET
    nodes: list[TxNode] = field(default_factory=list)
    edges: list[TxEdge] = field(default_factory=list)

    def _add(self, node: TxNode) -> TxNode:
        if any(existing.node_id == node.node_id for existing in self.nodes):
            raise PlanError(f"duplicate node id {node.node_id!r}")
        self.nodes.append(node)
        return node

    def link(self, source: str, target: str, when: EdgeWhen = EdgeWhen.SUCCESS) -> PlanBuilder:
        self.edges.append(TxEdge(source=source, target=target, when=when))
        return self

    def transfer(
        self,
        node_id: str,
        *,
        wallet_id: str,
        chain: Chain,
        asset: str,
        amount: str,
        destination: str,
        memo: str = "",
        label: str = "",
        params: dict[str, Any] | None = None,
        after: str | None = None,
        when: EdgeWhen = EdgeWhen.SUCCESS,
    ) -> PlanBuilder:
        self._add(
            TxNode(
                node_id=node_id,
                kind=NodeKind.TRANSFER,
                chain=chain,
                network=self.network,
                wallet_id=wallet_id,
                asset=asset,
                amount=str(amount),
                destination=destination,
                label=label,
                params={"memo": memo, **(params or {})},
            )
        )
        if after:
            self.link(after, node_id, when)
        return self

    def swap(
        self,
        node_id: str,
        *,
        wallet_id: str,
        chain: Chain,
        from_asset: str,
        amount: str,
        to_chain: Chain,
        to_asset: str,
        destination: str,
        min_amount_out: str | None = None,
        providers: list[str] | None = None,
        label: str = "",
        params: dict[str, Any] | None = None,
        after: str | None = None,
        when: EdgeWhen = EdgeWhen.SUCCESS,
    ) -> PlanBuilder:
        swap_params = {
            "to_chain": to_chain.value,
            "to_asset": to_asset,
            **(params or {}),
        }
        if min_amount_out is not None:
            swap_params["min_amount_out"] = str(min_amount_out)
        if providers:
            swap_params["providers"] = list(providers)
        self._add(
            TxNode(
                node_id=node_id,
                kind=NodeKind.SWAP,
                chain=chain,
                network=self.network,
                wallet_id=wallet_id,
                asset=from_asset,
                amount=str(amount),
                destination=destination,
                label=label,
                params=swap_params,
            )
        )
        if after:
            self.link(after, node_id, when)
        return self

    def approve(
        self,
        node_id: str,
        *,
        wallet_id: str,
        chain: Chain,
        asset: str,
        spender: str,
        amount: str | None = None,
        label: str = "",
        params: dict[str, Any] | None = None,
        after: str | None = None,
        when: EdgeWhen = EdgeWhen.SUCCESS,
    ) -> PlanBuilder:
        self._add(
            TxNode(
                node_id=node_id,
                kind=NodeKind.APPROVE,
                chain=chain,
                network=self.network,
                wallet_id=wallet_id,
                asset=asset,
                amount=str(amount or "0"),
                label=label,
                params={"spender": spender, **(params or {})},
            )
        )
        if after:
            self.link(after, node_id, when)
        return self

    def wait(
        self,
        node_id: str,
        *,
        tx_node: str,
        confirmations: int = 1,
        label: str = "",
        after: str | None = None,
        when: EdgeWhen = EdgeWhen.SUCCESS,
    ) -> PlanBuilder:
        self._add(
            TxNode(
                node_id=node_id,
                kind=NodeKind.WAIT,
                chain=Chain.BITCOIN,
                network=self.network,
                label=label,
                params={"tx_node": tx_node, "confirmations": int(confirmations)},
            )
        )
        if after:
            self.link(after, node_id, when)
        return self

    def build(
        self,
        *,
        name: str,
        plan_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        validate: bool = True,
    ) -> TransactionTree:
        tree = TransactionTree(
            plan_id=plan_id or new_plan_id(),
            name=name,
            network=self.network,
            nodes=list(self.nodes),
            edges=list(self.edges),
            created_at=now_iso(),
            metadata=dict(metadata or {}),
            state=PlanState.DRAFT,
        )
        if validate:
            tree.validate()
            tree.state = PlanState.VALIDATED
        return tree


def fan_out(
    *,
    name: str,
    funding_wallet: str,
    funding_chain: Chain,
    funding_asset: str,
    funding_amount: str,
    funding_destination: str,
    distributions: list[dict[str, Any]],
    network: Network = Network.TESTNET,
    metadata: dict[str, Any] | None = None,
) -> TransactionTree:
    """Fund one leg, then fan distributions out from its success.

    ``distributions`` entries are ``{wallet_id, chain, asset, amount,
    destination, label?, when?}``. An entry with ``when=failure`` is a fallback
    leg that runs only when the funding transfer failed.
    """
    if not distributions:
        raise PlanError("a fan-out plan needs at least one distribution")
    builder = PlanBuilder(network=network)
    builder.transfer(
        "fund",
        wallet_id=funding_wallet,
        chain=funding_chain,
        asset=funding_asset,
        amount=funding_amount,
        destination=funding_destination,
        label="funding leg",
    )
    for index, item in enumerate(distributions):
        node_id = str(item.get("node_id") or f"dist-{index + 1}")
        when = EdgeWhen(item.get("when", EdgeWhen.SUCCESS.value))
        builder.transfer(
            node_id,
            wallet_id=str(item["wallet_id"]),
            chain=Chain(item["chain"]),
            asset=str(item["asset"]),
            amount=str(item["amount"]),
            destination=str(item["destination"]),
            label=str(item.get("label", f"distribution {index + 1}")),
            params=item.get("params"),
            after="fund",
            when=when,
        )
    return builder.build(name=name, metadata=metadata)


def swap_with_fallback(
    *,
    name: str,
    wallet_id: str,
    chain: Chain,
    from_asset: str,
    amount: str,
    to_chain: Chain,
    to_asset: str,
    destination: str,
    providers: list[str] | None = None,
    network: Network = Network.TESTNET,
    min_amount_out: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TransactionTree:
    """Primary swap, then a fallback branch that runs only on failure.

    Both branches settle directly to ``destination``. The fallback re-quotes at
    execution time; it does not carry a stale quote from planning time.
    """
    builder = PlanBuilder(network=network)
    builder.swap(
        "swap-primary",
        wallet_id=wallet_id,
        chain=chain,
        from_asset=from_asset,
        amount=amount,
        to_chain=to_chain,
        to_asset=to_asset,
        destination=destination,
        providers=providers,
        min_amount_out=min_amount_out,
        label="primary swap",
    )
    builder.swap(
        "swap-fallback",
        wallet_id=wallet_id,
        chain=chain,
        from_asset=from_asset,
        amount=amount,
        to_chain=to_chain,
        to_asset=to_asset,
        destination=destination,
        providers=list(reversed(providers)) if providers else None,
        min_amount_out=min_amount_out,
        label="fallback swap",
        after="swap-primary",
        when=EdgeWhen.FAILURE,
    )
    return builder.build(name=name, metadata=metadata)


def describe(tree: TransactionTree) -> dict[str, Any]:
    """A scheduler view: layers, roots, leaves and branch edges."""
    tree.validate()
    layers = tree.topological_layers()
    targets = {edge.source for edge in tree.edges}
    return {
        "plan_id": tree.plan_id,
        "name": tree.name,
        "network": tree.network.value,
        "digest": tree.digest(),
        "layers": layers,
        "roots": [node.node_id for node in tree.nodes if node.node_id not in targets],
        "leaves": [
            node.node_id
            for node in tree.nodes
            if not any(edge.source == node.node_id for edge in tree.edges)
        ],
        "branches": [
            edge.to_dict()
            for edge in tree.edges
            if edge.when is not EdgeWhen.SUCCESS or edge.source == "swap-primary"
        ],
        "node_count": len(tree.nodes),
    }
