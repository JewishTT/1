"""Value objects for the SpecOps crypto transaction fabric.

The model is deliberately chain-neutral. A ``TransactionTree`` is a DAG of
``TxNode`` values joined by ``TxEdge`` values; an edge is taken only when its
``when`` predicate matches the source node's terminal state. That one rule is
what makes the planner branched rather than a linear batch: a swap can fan out
into a success path (settlement) and a failure path (fallback provider, then
alert), and independent transfers can run as parallel layers.

Amounts are decimal strings, never floats. Base-unit conversion is exact and
raises instead of rounding a satoshi or a wei away.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Chain(StrEnum):
    ETHEREUM = "ethereum"
    TRON = "tron"
    BITCOIN = "bitcoin"


class Network(StrEnum):
    MAINNET = "mainnet"
    TESTNET = "testnet"


class NodeKind(StrEnum):
    TRANSFER = "transfer"
    SWAP = "swap"
    APPROVE = "approve"
    WAIT = "wait"
    NOOP = "noop"


class NodeState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def terminal(self) -> bool:
        return self in {NodeState.SUCCEEDED, NodeState.FAILED, NodeState.SKIPPED}


class PlanState(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EdgeWhen(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    ALWAYS = "always"


@dataclass(frozen=True)
class Asset:
    """A chain asset. ``contract`` is ``None`` for the native coin."""

    chain: Chain
    symbol: str
    decimals: int
    contract: str | None = None

    @property
    def native(self) -> bool:
        return self.contract is None

    def to_base_units(self, amount: Decimal | str) -> int:
        value = _decimal(amount)
        scaled = value * (Decimal(10) ** self.decimals)
        if scaled != scaled.to_integral_value():
            raise ValueError(
                f"{value} {self.symbol} has more than {self.decimals} decimal places"
            )
        return int(scaled)

    def from_base_units(self, units: int) -> Decimal:
        return Decimal(units) / (Decimal(10) ** self.decimals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "contract": self.contract,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Asset:
        return cls(
            chain=Chain(data["chain"]),
            symbol=str(data["symbol"]),
            decimals=int(data["decimals"]),
            contract=data.get("contract"),
        )


#: Assets the fabric can name without a network read. A caller may pass an
#: explicit contract in a node's params for anything else, which is how the
#: long tail stays reachable without pretending this table is exhaustive.
KNOWN_ASSETS: dict[tuple[Chain, Network, str], Asset] = {
    (Chain.ETHEREUM, Network.MAINNET, "ETH"): Asset(Chain.ETHEREUM, "ETH", 18),
    (Chain.ETHEREUM, Network.TESTNET, "ETH"): Asset(Chain.ETHEREUM, "ETH", 18),
    (Chain.ETHEREUM, Network.MAINNET, "USDC"): Asset(
        Chain.ETHEREUM, "USDC", 6, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    ),
    (Chain.ETHEREUM, Network.TESTNET, "USDC"): Asset(
        Chain.ETHEREUM, "USDC", 6, "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
    ),
    (Chain.TRON, Network.MAINNET, "TRX"): Asset(Chain.TRON, "TRX", 6),
    (Chain.TRON, Network.TESTNET, "TRX"): Asset(Chain.TRON, "TRX", 6),
    (Chain.TRON, Network.MAINNET, "USDT"): Asset(
        Chain.TRON, "USDT", 6, "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    ),
    (Chain.BITCOIN, Network.MAINNET, "BTC"): Asset(Chain.BITCOIN, "BTC", 8),
    (Chain.BITCOIN, Network.TESTNET, "BTC"): Asset(Chain.BITCOIN, "BTC", 8),
}


def resolve_asset(
    chain: Chain,
    network: Network,
    symbol: str,
    *,
    contract: str | None = None,
    decimals: int | None = None,
) -> Asset:
    if contract is None and decimals is None:
        asset = KNOWN_ASSETS.get((chain, network, symbol.upper()))
        if asset is not None:
            return asset
        raise ValueError(
            f"{symbol} on {chain.value}/{network.value} is not a known native asset; "
            "pass contract and decimals"
        )
    if contract is None or decimals is None:
        raise ValueError("contract and decimals must be supplied together")
    return Asset(chain=chain, symbol=symbol.upper(), decimals=int(decimals), contract=contract)


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a decimal amount: {value!r}") from exc


@dataclass
class TxNode:
    node_id: str
    kind: NodeKind
    chain: Chain
    wallet_id: str | None = None
    asset: str = ""
    amount: str = "0"
    destination: str | None = None
    network: Network = Network.TESTNET
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    timeout_s: int = 300

    def decimal_amount(self) -> Decimal:
        return _decimal(self.amount)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "chain": self.chain.value,
            "wallet_id": self.wallet_id,
            "asset": self.asset,
            "amount": str(self.amount),
            "destination": self.destination,
            "network": self.network.value,
            "params": dict(self.params),
            "label": self.label,
            "timeout_s": int(self.timeout_s),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxNode:
        return cls(
            node_id=str(data["node_id"]),
            kind=NodeKind(data["kind"]),
            chain=Chain(data["chain"]),
            wallet_id=data.get("wallet_id"),
            asset=str(data.get("asset", "")),
            amount=str(data.get("amount", "0")),
            destination=data.get("destination"),
            network=Network(data.get("network", Network.TESTNET.value)),
            params=dict(data.get("params") or {}),
            label=str(data.get("label", "")),
            timeout_s=int(data.get("timeout_s", 300)),
        )


@dataclass(frozen=True)
class TxEdge:
    source: str
    target: str
    when: EdgeWhen = EdgeWhen.SUCCESS

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "when": self.when.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxEdge:
        return cls(
            source=str(data["source"]),
            target=str(data["target"]),
            when=EdgeWhen(data.get("when", EdgeWhen.SUCCESS.value)),
        )


@dataclass
class TransactionTree:
    """A branched, acyclic plan. All money movement is represented here."""

    plan_id: str
    name: str
    nodes: list[TxNode]
    edges: list[TxEdge]
    network: Network = Network.TESTNET
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    state: PlanState = PlanState.DRAFT

    @property
    def node_map(self) -> dict[str, TxNode]:
        return {node.node_id: node for node in self.nodes}

    def validate(self) -> TransactionTree:
        from specops.cryptotx.errors import PlanError

        if not self.plan_id.strip():
            raise PlanError("plan_id is required")
        if not self.nodes:
            raise PlanError("a plan needs at least one node")
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            duplicates = sorted({n for n in ids if ids.count(n) > 1})
            raise PlanError("duplicate node ids", nodes=duplicates)
        known = set(ids)
        for node in self.nodes:
            _validate_node(node)
        for edge in self.edges:
            if edge.source not in known:
                raise PlanError(f"edge source {edge.source!r} is not a node")
            if edge.target not in known:
                raise PlanError(f"edge target {edge.target!r} is not a node")
            if edge.source == edge.target:
                raise PlanError(f"self-edge on {edge.source!r}")
        self.topological_layers()
        return self

    def topological_order(self) -> list[str]:
        layers = self.topological_layers()
        return [node for layer in layers for node in layer]

    def topological_layers(self) -> list[list[str]]:
        from specops.cryptotx.errors import PlanError

        ids = [node.node_id for node in self.nodes]
        indegree = {node_id: 0 for node_id in ids}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in ids}
        for edge in self.edges:
            indegree[edge.target] += 1
            outgoing[edge.source].append(edge.target)
        ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        layers: list[list[str]] = []
        seen = 0
        while ready:
            layer = ready
            layers.append(layer)
            seen += len(layer)
            next_ready: list[str] = []
            for node_id in layer:
                for target in outgoing[node_id]:
                    indegree[target] -= 1
                    if indegree[target] == 0:
                        next_ready.append(target)
            ready = sorted(next_ready)
        if seen != len(ids):
            cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
            raise PlanError("plan contains a cycle", nodes=cyclic)
        return layers

    def digest(self) -> str:
        payload = {
            "version": self.version,
            "plan_id": self.plan_id,
            "name": self.name,
            "network": self.network.value,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": self.metadata,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "network": self.network.value,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "version": self.version,
            "state": self.state.value,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransactionTree:
        return cls(
            plan_id=str(data["plan_id"]),
            name=str(data.get("name", "")),
            nodes=[TxNode.from_dict(item) for item in data.get("nodes", [])],
            edges=[TxEdge.from_dict(item) for item in data.get("edges", [])],
            network=Network(data.get("network", Network.TESTNET.value)),
            created_at=str(data.get("created_at") or now_iso()),
            metadata=dict(data.get("metadata") or {}),
            version=int(data.get("version", 1)),
            state=PlanState(data.get("state", PlanState.DRAFT.value)),
        )


def _validate_node(node: TxNode) -> None:
    from specops.cryptotx.errors import PlanError

    if node.kind is NodeKind.TRANSFER:
        if not node.destination:
            raise PlanError(f"transfer node {node.node_id!r} has no destination")
        if node.decimal_amount() <= 0:
            raise PlanError(f"transfer node {node.node_id!r} has a non-positive amount")
    if node.kind is NodeKind.SWAP:
        if not node.destination:
            raise PlanError(f"swap node {node.node_id!r} has no recipient")
        if node.decimal_amount() <= 0:
            raise PlanError(f"swap node {node.node_id!r} has a non-positive amount")
        for key in ("to_chain", "to_asset"):
            if not node.params.get(key):
                raise PlanError(f"swap node {node.node_id!r} is missing params.{key}")
    if node.kind is NodeKind.APPROVE:
        if not node.params.get("spender"):
            raise PlanError(f"approve node {node.node_id!r} is missing params.spender")
    if node.network is Network.MAINNET and node.params.get("allow_mainnet") is False:
        raise PlanError(f"node {node.node_id!r} explicitly disallows mainnet")


@dataclass(frozen=True)
class Wallet:
    """Public wallet metadata. The key material lives only in the vault."""

    wallet_id: str
    label: str
    chain: Chain
    network: Network
    address: str
    derivation_path: str
    account_index: int
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Wallet:
        return cls(
            wallet_id=str(data["wallet_id"]),
            label=str(data.get("label", "")),
            chain=Chain(data["chain"]),
            network=Network(data["network"]),
            address=str(data["address"]),
            derivation_path=str(data["derivation_path"]),
            account_index=int(data.get("account_index", 0)),
            created_at=str(data.get("created_at") or now_iso()),
        )


@dataclass
class PreparedTransaction:
    chain: Chain
    network: Network
    from_address: str
    to_address: str
    asset: Asset
    amount: Decimal
    fee: Decimal
    payload: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    tx_hash: str | None = None
    fee_detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "network": self.network.value,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "asset": self.asset.to_dict(),
            "amount": str(self.amount),
            "fee": str(self.fee),
            "payload": dict(self.payload),
            "description": self.description,
            "tx_hash": self.tx_hash,
            "fee_detail": dict(self.fee_detail),
        }


@dataclass
class SignedTransaction:
    chain: Chain
    network: Network
    tx_hash: str
    raw: str | dict[str, Any]
    prepared: PreparedTransaction

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "network": self.network.value,
            "tx_hash": self.tx_hash,
            "raw": self.raw,
            "prepared": self.prepared.to_dict(),
        }


@dataclass
class SwapInstruction:
    kind: str
    chain: Chain
    to: str
    asset: str
    amount: Decimal = Decimal(0)
    value: Decimal = Decimal(0)
    calldata: str = ""
    memo: str = ""
    fee_limit: int = 0
    description: str = ""
    approval_spender: str | None = None
    approval_asset: str | None = None
    approval_amount: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "chain": self.chain.value,
            "to": self.to,
            "asset": self.asset,
            "amount": str(self.amount),
            "value": str(self.value),
            "calldata": self.calldata,
            "memo": self.memo,
            "fee_limit": self.fee_limit,
            "description": self.description,
            "approval_spender": self.approval_spender,
            "approval_asset": self.approval_asset,
            "approval_amount": self.approval_amount,
            "extra": dict(self.extra),
        }


@dataclass
class SwapQuote:
    provider: str
    from_chain: Chain
    to_chain: Chain
    from_asset: str
    to_asset: str
    amount_in: Decimal
    expected_amount_out: Decimal
    min_amount_out: Decimal
    from_address: str
    to_address: str
    route: str
    expires_at: str | None = None
    instruction: SwapInstruction | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    fee_native: Decimal = Decimal(0)
    fee_asset: str = ""

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = {
            "provider": self.provider,
            "from_chain": self.from_chain.value,
            "to_chain": self.to_chain.value,
            "from_asset": self.from_asset,
            "to_asset": self.to_asset,
            "amount_in": str(self.amount_in),
            "expected_amount_out": str(self.expected_amount_out),
            "min_amount_out": str(self.min_amount_out),
            "from_address": self.from_address,
            "to_address": self.to_address,
            "route": self.route,
            "expires_at": self.expires_at,
            "instruction": self.instruction.to_dict() if self.instruction else None,
            "fee_native": str(self.fee_native),
            "fee_asset": self.fee_asset,
        }
        if include_raw:
            data["raw"] = self.raw
        return data


@dataclass
class NodeResult:
    node_id: str
    state: NodeState
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    tx_hash: str | None = None
    provider: str | None = None
    prepared: dict[str, Any] | None = None
    signed: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    run_id: str
    plan_id: str
    plan_digest: str
    dry_run: bool
    state: PlanState
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "dry_run": self.dry_run,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "node_results": {
                node_id: result.to_dict() for node_id, result in self.node_results.items()
            },
            "notes": list(self.notes),
        }
