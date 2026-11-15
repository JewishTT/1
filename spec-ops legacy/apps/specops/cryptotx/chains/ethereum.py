"""Ethereum adapter: EIP-1559 transfers, ERC20 calls and local signing.

Signing is ``eth-account``'s implementation of the typed transaction; address
validation and checksumming are ``eth-utils``. The adapter reads nonce, gas and
fees from the configured JSON-RPC endpoint and never falls back to a hard-coded
mainnet value.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_utils import is_address, keccak, to_checksum_address

from specops.cryptotx import hd
from specops.cryptotx.chains.base import BroadcastReceipt, ChainAdapter, JsonRpc
from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import ChainError
from specops.cryptotx.models import (
    Asset,
    Chain,
    Network,
    PreparedTransaction,
    SignedTransaction,
    SwapInstruction,
)

_CHAIN_IDS = {Network.MAINNET: 1, Network.TESTNET: 11155111}
_WEI = Decimal(10) ** 18
_GWEI = Decimal(10) ** 9
_MAX_UINT256 = 2**256 - 1


def selector(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


def encode_call(signature: str, types: list[str], values: list[Any]) -> str:
    return selector(signature) + abi_encode(types, values).hex()


class EthereumAdapter(ChainAdapter):
    chain = Chain.ETHEREUM

    def __init__(
        self,
        config: CryptoTxConfig,
        network: Network,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.network = network
        self.rpc = JsonRpc(
            config.eth_rpc[network],
            timeout=config.request_timeout_s,
            retries=config.max_retries,
            transport=transport,
        )
        self._chain_id: int | None = None

    def close(self) -> None:
        self.rpc.close()

    def native_asset(self) -> Asset:
        return Asset(Chain.ETHEREUM, "ETH", 18)

    def chain_id(self) -> int:
        if self._chain_id is None:
            value = self.rpc.call("eth_chainId", [])
            self._chain_id = int(value, 16) if isinstance(value, str) else int(value)
        return self._chain_id

    def validate_address(self, address: str) -> str:
        if not is_address(address):
            raise ChainError(f"not an Ethereum address: {address!r}")
        return to_checksum_address(address)

    def get_balance(self, address: str, asset: Asset) -> Decimal:
        address = self.validate_address(address)
        if asset.native:
            result = self.rpc.call("eth_getBalance", [address, "latest"])
            return Decimal(int(result, 16)) / _WEI
        result = self.rpc.call(
            "eth_call",
            [
                {
                    "to": self.validate_address(asset.contract or ""),
                    "data": encode_call("balanceOf(address)", ["address"], [address]),
                },
                "latest",
            ],
        )
        return asset.from_base_units(int(result, 16))

    def _fee_fields(self) -> tuple[int, int]:
        try:
            tip = int(self.rpc.call("eth_maxPriorityFeePerGas", []), 16)
        except ChainError:
            tip = int(Decimal(1) * _GWEI)
        block = self.rpc.call("eth_getBlockByNumber", ["latest", False]) or {}
        base_fee_raw = block.get("baseFeePerGas")
        if base_fee_raw is None:
            gas_price = int(self.rpc.call("eth_gasPrice", []), 16)
            return gas_price, gas_price
        base_fee = int(base_fee_raw, 16)
        max_fee = base_fee * 2 + tip
        return max_fee, tip

    def _estimate_gas(self, transaction: dict[str, Any], fallback: int) -> int:
        try:
            raw = self.rpc.call("eth_estimateGas", [transaction])
            return max(21_000, int(int(raw, 16) * 1.2))
        except ChainError:
            return fallback

    def _build(
        self,
        material: hd.DerivedKey,
        *,
        to: str,
        value_wei: int,
        data: str,
        asset: Asset,
        amount: Decimal,
        description: str,
        gas_fallback: int,
        fee_detail_extra: dict[str, Any] | None = None,
    ) -> PreparedTransaction:
        sender = self.validate_address(material.address)
        nonce = int(
            self.rpc.call("eth_getTransactionCount", [sender, "pending"]), 16
        )
        max_fee, tip = self._fee_fields()
        candidate = {"from": sender, "to": to, "value": hex(value_wei), "data": data}
        gas = self._estimate_gas(candidate, gas_fallback)
        transaction = {
            "type": 2,
            "chainId": self.chain_id(),
            "nonce": nonce,
            "maxPriorityFeePerGas": tip,
            "maxFeePerGas": max_fee,
            "gas": gas,
            "to": to,
            "value": value_wei,
            "data": data,
        }
        fee_wei = gas * max_fee
        detail = {
            "nonce": nonce,
            "gas": gas,
            "max_fee_gwei": str(Decimal(max_fee) / _GWEI),
            "priority_fee_gwei": str(Decimal(tip) / _GWEI),
            "fee_wei": fee_wei,
        }
        if fee_detail_extra:
            detail.update(fee_detail_extra)
        return PreparedTransaction(
            chain=Chain.ETHEREUM,
            network=self.network,
            from_address=sender,
            to_address=to,
            asset=asset,
            amount=amount,
            fee=Decimal(fee_wei) / _WEI,
            payload={"transaction": transaction},
            description=description,
            fee_detail=detail,
        )

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
        to = self.validate_address(to_address)
        if asset.native:
            if memo:
                raise ChainError("native ETH transfers carry no memo; use a contract call")
            units = asset.to_base_units(amount)
            return self._build(
                material,
                to=to,
                value_wei=units,
                data="0x",
                asset=asset,
                amount=amount,
                description=f"send {amount} ETH",
                gas_fallback=21_000,
            )
        if not asset.contract:
            raise ChainError(f"asset {asset.symbol} has no ERC20 contract")
        units = asset.to_base_units(amount)
        data = encode_call("transfer(address,uint256)", ["address", "uint256"], [to, units])
        return self._build(
            material,
            to=self.validate_address(asset.contract),
            value_wei=0,
            data=data,
            asset=asset,
            amount=amount,
            description=f"send {amount} {asset.symbol}",
            gas_fallback=65_000,
            fee_detail_extra={"token": asset.contract},
        )

    def prepare_approve(
        self,
        material: hd.DerivedKey,
        asset: Asset,
        spender: str,
        *,
        amount: Decimal | None = None,
    ) -> PreparedTransaction:
        if asset.native or not asset.contract:
            raise ChainError("approve requires an ERC20 asset")
        allowance = _MAX_UINT256 if amount is None else asset.to_base_units(amount)
        data = encode_call(
            "approve(address,uint256)", ["address", "uint256"],
            [self.validate_address(spender), allowance],
        )
        return self._build(
            material,
            to=self.validate_address(asset.contract),
            value_wei=0,
            data=data,
            asset=asset,
            amount=Decimal(0),
            description=f"approve {spender} for {asset.symbol}",
            gas_fallback=55_000,
            fee_detail_extra={"spender": spender, "allowance": str(allowance)},
        )

    def prepare_call(
        self,
        material: hd.DerivedKey,
        instruction: SwapInstruction,
        *,
        asset: Asset,
    ) -> PreparedTransaction:
        if instruction.chain is not Chain.ETHEREUM:
            raise ChainError("instruction is not an Ethereum call")
        if not instruction.calldata:
            raise ChainError("swap instruction has no calldata")
        to = self.validate_address(instruction.to)
        return self._build(
            material,
            to=to,
            value_wei=asset.to_base_units(instruction.value) if instruction.value else 0,
            data=instruction.calldata,
            asset=asset,
            amount=instruction.amount,
            description=instruction.description or "EVM contract call",
            gas_fallback=350_000,
            fee_detail_extra={"kind": instruction.kind},
        )

    def sign(self, prepared: PreparedTransaction, material: hd.DerivedKey) -> SignedTransaction:
        try:
            signed = Account.sign_transaction(
                prepared.payload["transaction"], material.private_key
            )
        except Exception as exc:  # noqa: BLE001 - library boundary
            raise ChainError("eth-account refused to sign the transaction") from exc
        raw = signed.raw_transaction.hex()
        if not raw.startswith("0x"):
            raw = "0x" + raw
        tx_hash = signed.hash.hex()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return SignedTransaction(
            chain=Chain.ETHEREUM,
            network=self.network,
            tx_hash=tx_hash,
            raw=raw,
            prepared=prepared,
        )

    def broadcast(self, signed: SignedTransaction) -> BroadcastReceipt:
        if signed.chain is not Chain.ETHEREUM:
            raise ChainError("signed transaction is not Ethereum")
        try:
            returned = self.rpc.send_raw(str(signed.raw))
        except Exception as exc:  # noqa: BLE001 - RPC failure must remain typed
            raise ChainError(f"Ethereum broadcast failed: {exc}") from exc
        return BroadcastReceipt(
            tx_hash=returned or signed.tx_hash,
            accepted=True,
            detail={"endpoint": self.network.value, "rpc_hash": returned},
        )

    def confirmations(self, tx_hash: str) -> int:
        receipt = self.rpc.call("eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            return 0
        if int(receipt.get("status", "0x0"), 16) == 0:
            return 0
        block = int(receipt["blockNumber"], 16)
        latest = int(self.rpc.call("eth_blockNumber", []), 16)
        return max(1, latest - block + 1)

    def allowance(self, owner: str, spender: str, token: str) -> Decimal:
        result = self.rpc.call(
            "eth_call",
            [
                {
                    "to": self.validate_address(token),
                    "data": encode_call(
                        "allowance(address,address)",
                        ["address", "address"],
                        [self.validate_address(owner), self.validate_address(spender)],
                    ),
                },
                "latest",
            ],
        )
        return Decimal(int(result, 16))

