"""Chain-adapter contract and shared HTTP/RPC plumbing."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from specops.cryptotx import hd
from specops.cryptotx.errors import RpcError
from specops.cryptotx.models import (
    Asset,
    Chain,
    Network,
    PreparedTransaction,
    SignedTransaction,
    SwapInstruction,
)


@dataclass(frozen=True)
class BroadcastReceipt:
    tx_hash: str
    accepted: bool
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"tx_hash": self.tx_hash, "accepted": self.accepted, "detail": self.detail}


class JsonRpc:
    """Minimal JSON-RPC client. Retries only idempotent calls.

    Broadcasting is the one call that must never be retried blindly: an
    ``eth_sendRawTransaction`` timeout does not mean the transaction was
    rejected, and resending it is at best a no-op and at worst a double spend.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 20.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.retries = max(0, retries)
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._next_id = 1

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method,
                   "params": params or []}
        self._next_id += 1
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post(self.url, json=payload)
                if response.status_code >= 500:
                    raise RpcError(f"{method} returned HTTP {response.status_code}")
                body = response.json()
                if "error" in body and body["error"]:
                    error = body["error"]
                    message = (
                        error.get("message", "rpc error")
                        if isinstance(error, dict)
                        else str(error)
                    )
                    raise RpcError(f"{method} refused: {message}")
                return body.get("result")
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.15 * (attempt + 1))
        raise RpcError(f"{method} failed after {self.retries + 1} attempt(s): {last_error}")

    def send_raw(self, raw_hex: str) -> str:
        return str(self.call("eth_sendRawTransaction", [raw_hex]))


class ChainAdapter(ABC):
    """One chain, one network. Adapters never decide policy or approvals."""

    chain: Chain
    network: Network

    @abstractmethod
    def validate_address(self, address: str) -> str:
        """Return the canonical address or raise ``ChainError``."""

    @abstractmethod
    def get_balance(self, address: str, asset: Asset) -> Decimal:
        """Balance in display units (not base units)."""

    @abstractmethod
    def prepare_transfer(
        self,
        material: hd.DerivedKey,
        to_address: str,
        asset: Asset,
        amount: Decimal,
        *,
        memo: str = "",
        fee_rate: Decimal | None = None,
        **kwargs: Any,
    ) -> PreparedTransaction:
        """Build an unsigned transaction. No key is needed for this step."""

    @abstractmethod
    def prepare_call(
        self,
        material: hd.DerivedKey,
        instruction: SwapInstruction,
        *,
        asset: Asset,
    ) -> PreparedTransaction:
        """Build an unsigned contract call from a swap instruction."""

    @abstractmethod
    def sign(self, prepared: PreparedTransaction, material: hd.DerivedKey) -> SignedTransaction:
        """Sign locally. The private key never leaves this call."""

    @abstractmethod
    def broadcast(self, signed: SignedTransaction) -> BroadcastReceipt:
        """Send a signed transaction. Called only after the policy gate."""

    @abstractmethod
    def confirmations(self, tx_hash: str) -> int:
        """Number of confirmations, 0 when pending, -1 when unknown."""

    def native_balance(self, address: str) -> Decimal:
        return self.get_balance(address, self.native_asset())

    @abstractmethod
    def native_asset(self) -> Asset:
        """The chain's fee asset."""

    @abstractmethod
    def close(self) -> None:
        """Release any connection pool. Idempotent."""
