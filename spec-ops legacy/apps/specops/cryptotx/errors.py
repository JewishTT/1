"""Typed refusals for the SpecOps crypto transaction fabric.

Every refusal carries a stable ``code``; routers map the code to a status rather
than parsing prose. The rule from the rest of the department applies here too:
a live money-moving step is *blocked* in code, never merely warned about in a
view.

Nothing in this module accepts, stores or renders a private key.
"""

from __future__ import annotations


class CryptoTxError(Exception):
    """Base for every refusal raised by the transaction fabric."""

    code = "cryptotx-error"

    def __init__(self, reason: str, **context: object) -> None:
        super().__init__(reason)
        self.reason = reason
        self.context = context

    def to_wire(self) -> dict[str, object]:
        return {"error": self.code, "detail": self.reason, **self.context}


class VaultError(CryptoTxError):
    """The encrypted wallet vault could not be read, unlocked or written."""

    code = "VaultError"


class VaultLocked(VaultError):
    """An operation needed the mnemonic but the vault was still locked."""

    code = "VaultLocked"


class WalletNotFound(VaultError):
    """No wallet with the requested id exists in the vault."""

    code = "WalletNotFound"


class ChainError(CryptoTxError):
    """A chain adapter refused or failed a chain-specific operation."""

    code = "ChainError"


class RpcError(ChainError):
    """An RPC/HTTP endpoint returned an error or an unusable answer."""

    code = "RpcError"


class PlanError(CryptoTxError):
    """A transaction tree is structurally invalid."""

    code = "PlanError"


class PolicyError(CryptoTxError):
    """A hard policy boundary refused the transaction (Constitution P11)."""

    code = "PolicyError"


class ApprovalRequired(PolicyError):
    """Live execution was attempted without a valid approval token."""

    code = "ApprovalRequired"


class SwapError(CryptoTxError):
    """No provider could quote or build the requested swap."""

    code = "SwapError"


class SwapUnavailable(SwapError):
    """The requested pair is outside every configured provider's coverage."""

    code = "SwapUnavailable"


class NodeFailed(CryptoTxError):
    """A transaction-tree node failed; the scheduler handles the branch."""

    code = "NodeFailed"


class StoreError(CryptoTxError):
    """The plan/run ledger is unavailable or corrupt."""

    code = "StoreError"
