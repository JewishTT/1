"""SpecOps cryptocurrency transaction fabric.

A branched planner, local signing and policy-gated broadcasting across
Ethereum, TRON and Bitcoin. Start with :mod:`specops.cryptotx.planner` to build
a plan and :mod:`specops.cryptotx.executor` to run it.
"""

from specops.cryptotx.config import CryptoTxConfig, get_config
from specops.cryptotx.errors import (
    ApprovalRequired,
    ChainError,
    CryptoTxError,
    NodeFailed,
    PlanError,
    PolicyError,
    RpcError,
    SwapError,
    SwapUnavailable,
    VaultError,
    WalletNotFound,
)
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
    PreparedTransaction,
    SignedTransaction,
    SwapInstruction,
    SwapQuote,
    TransactionTree,
    TxEdge,
    TxNode,
    Wallet,
)

__all__ = [
    "ApprovalRequired",
    "Asset",
    "Chain",
    "ChainError",
    "CryptoTxConfig",
    "CryptoTxError",
    "EdgeWhen",
    "ExecutionResult",
    "Network",
    "NodeFailed",
    "NodeKind",
    "NodeResult",
    "NodeState",
    "PlanError",
    "PlanState",
    "PolicyError",
    "PreparedTransaction",
    "RpcError",
    "SignedTransaction",
    "SwapError",
    "SwapInstruction",
    "SwapQuote",
    "SwapUnavailable",
    "TransactionTree",
    "TxEdge",
    "TxNode",
    "VaultError",
    "Wallet",
    "WalletNotFound",
    "get_config",
]
