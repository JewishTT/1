"""TRON adapter: TRX and TRC20 transfers, contract triggers and local signing.

``tronpy`` supplies address encoding, the transaction builder and the signature
primitive. Transactions are built against a recently-solid block reference and
signed locally with the derived key; the API only ever sees the signed payload.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tronpy import Tron
from tronpy.abi import trx_abi
from tronpy.contract import Contract
from tronpy.keys import PrivateKey, is_base58check_address, to_hex_address
from tronpy.providers import HTTPProvider
from tronpy.tron import Transaction, TransactionBuilder

from specops.cryptotx import hd
from specops.cryptotx.chains.base import BroadcastReceipt, ChainAdapter
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

_SUN = Decimal(10) ** 6
_DEFAULT_FEE_LIMIT_SUN = 30_000_000
_TRC20_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


def _selector(signature: str) -> str:
    from eth_utils import keccak

    return keccak(text=signature)[:4].hex()


def _encode(function: str, types: str, values: list[Any]) -> str:
    return _selector(function) + trx_abi.encode_single(types, values).hex()


class TronAdapter(ChainAdapter):
    chain = Chain.TRON

    def __init__(
        self,
        config: CryptoTxConfig,
        network: Network,
        *,
        client: Tron | None = None,
    ) -> None:
        self.config = config
        self.network = network
        self._injected = client
        self._own_client: Tron | None = None

    def client(self) -> Tron:
        if self._injected is not None:
            return self._injected
        if self._own_client is None:
            provider = HTTPProvider(
                self.config.tron_endpoint[self.network],
                timeout=self.config.request_timeout_s,
                api_key=self.config.tron_api_key,
            )
            self._own_client = Tron(provider)
        return self._own_client

    def close(self) -> None:
        if self._own_client is not None:
            self._own_client = None

    def native_asset(self) -> Asset:
        return Asset(Chain.TRON, "TRX", 6)

    def validate_address(self, address: str) -> str:
        if not is_base58check_address(address):
            raise ChainError(f"not a TRON base58 address: {address!r}")
        return address

    def get_balance(self, address: str, asset: Asset) -> Decimal:
        address = self.validate_address(address)
        client = self.client()
        if asset.native:
            return Decimal(client.get_account_balance(address))
        if not asset.contract:
            raise ChainError(f"{asset.symbol} has no TRC20 contract")
        contract = Contract(asset.contract, abi=_TRC20_ABI, client=client)
        raw = contract.functions.balanceOf(address)
        return asset.from_base_units(int(raw or 0))

    def _energy_fee(self, owner: str, contract: str, data: str) -> Decimal:
        client = self.client()
        try:
            energy = client.get_estimated_energy(
                owner, contract, data[:8], data[8:]
            )
            params = client.get_chain_parameters()
            price = int(params.get("getEnergyFee", 100))
            total_sun = int(energy) * price
            return Decimal(total_sun) / _SUN
        except Exception:  # noqa: BLE001 - estimate is best-effort, never fabricated
            return Decimal(0)

    def _fee_estimate(self, owner: str, asset: Asset, data: str) -> tuple[Decimal, int]:
        if asset.native:
            return Decimal("0.3"), 0
        fee_limit = int(
            self.config.extra.get(
                "tron_fee_limit_sun", str(_DEFAULT_FEE_LIMIT_SUN)
            )
        )
        energy_fee = self._energy_fee(owner, asset.contract or "", data)
        if energy_fee <= 0:
            energy_fee = Decimal("15")
        fee = min(energy_fee + Decimal("0.3"), Decimal(fee_limit) / _SUN)
        return fee, fee_limit

    def _trigger(
        self,
        material: hd.DerivedKey,
        *,
        to: str,
        data: str,
        value_sun: int,
        description: str,
        fee_limit_sun: int,
        asset: Asset,
        amount: Decimal,
        fee: Decimal,
    ) -> PreparedTransaction:
        client = self.client()
        sender = self.validate_address(material.address)
        inner = {
            "parameter": {
                "value": {
                    "owner_address": to_hex_address(sender),
                    "contract_address": to_hex_address(self.validate_address(to)),
                    "data": data.removeprefix("0x"),
                    "call_value": value_sun,
                    "call_token_value": 0,
                    "token_id": 0,
                },
                "type_url": "type.googleapis.com/protocol.TriggerSmartContract",
            },
            "type": "TriggerSmartContract",
        }
        builder = TransactionBuilder(inner, client=client)
        if fee_limit_sun:
            builder.fee_limit(fee_limit_sun)
        tx = builder.build()
        return PreparedTransaction(
            chain=Chain.TRON,
            network=self.network,
            from_address=sender,
            to_address=to,
            asset=asset,
            amount=amount,
            fee=fee,
            payload={
                "tx": tx.to_json(),
                "kind": "trigger_smart_contract",
                "fee_limit_sun": fee_limit_sun,
                "calldata": data,
            },
            description=description,
            tx_hash=tx.txid,
            fee_detail={"fee_limit_sun": fee_limit_sun, "value_sun": value_sun},
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
        sender = self.validate_address(material.address)
        to = self.validate_address(to_address)
        units = asset.to_base_units(amount)
        client = self.client()
        if asset.native:
            builder = client.trx.transfer(sender, to, units)
            if memo:
                builder.memo(memo)
            tx = builder.build()
            fee_sun = int(kwargs.get("fee_sun", 300_000))
            return PreparedTransaction(
                chain=Chain.TRON,
                network=self.network,
                from_address=sender,
                to_address=to,
                asset=asset,
                amount=amount,
                fee=Decimal(fee_sun) / _SUN,
                payload={"tx": tx.to_json(), "kind": "trx_transfer"},
                description=f"send {amount} TRX",
                tx_hash=tx.txid,
                fee_detail={"fee_sun": fee_sun},
            )
        if not asset.contract:
            raise ChainError(f"{asset.symbol} has no TRC20 contract")
        data = _encode("transfer(address,uint256)", "(address,uint256)", [to, units])
        fee, fee_limit = self._fee_estimate(sender, asset, data)
        contract = Contract(asset.contract, abi=_TRC20_ABI, client=client)
        builder = contract.functions.transfer(to, units).with_owner(sender)
        if fee_limit:
            builder.fee_limit(fee_limit)
        if memo:
            builder.memo(memo)
        tx = builder.build()
        return PreparedTransaction(
            chain=Chain.TRON,
            network=self.network,
            from_address=sender,
            to_address=to,
            asset=asset,
            amount=amount,
            fee=fee,
            payload={
                "tx": tx.to_json(),
                "kind": "trc20_transfer",
                "fee_limit_sun": fee_limit,
                "calldata": data,
            },
            description=f"send {amount} {asset.symbol}",
            tx_hash=tx.txid,
            fee_detail={"fee_limit_sun": fee_limit, "token": asset.contract},
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
            raise ChainError("approve requires a TRC20 asset")
        units = (2**256 - 1) if amount is None else asset.to_base_units(amount)
        data = _encode(
            "approve(address,uint256)", "(address,uint256)",
            [self.validate_address(spender), units],
        )
        fee, fee_limit = self._fee_estimate(material.address, asset, data)
        return self._trigger(
            material,
            to=asset.contract,
            data=data,
            value_sun=0,
            description=f"approve {spender} for {asset.symbol}",
            fee_limit_sun=fee_limit,
            asset=asset,
            amount=Decimal(0),
            fee=fee,
        )

    def prepare_call(
        self,
        material: hd.DerivedKey,
        instruction: SwapInstruction,
        *,
        asset: Asset,
    ) -> PreparedTransaction:
        if instruction.chain is not Chain.TRON:
            raise ChainError("instruction is not a TRON call")
        if not instruction.calldata:
            raise ChainError("swap instruction has no calldata")
        value_sun = asset.to_base_units(instruction.value) if instruction.value else 0
        fee, default_limit = self._fee_estimate(material.address, asset, instruction.calldata)
        limit = instruction.fee_limit or default_limit
        return self._trigger(
            material,
            to=instruction.to,
            data=instruction.calldata,
            value_sun=value_sun,
            description=instruction.description or "TRON contract call",
            fee_limit_sun=limit,
            asset=asset,
            amount=instruction.amount,
            fee=fee,
        )

    def sign(self, prepared: PreparedTransaction, material: hd.DerivedKey) -> SignedTransaction:
        if prepared.chain is not Chain.TRON:
            raise ChainError("prepared transaction is not TRON")
        transaction = Transaction.from_json(
            prepared.payload["tx"], client=self._injected
        )
        try:
            transaction.sign(PrivateKey(material.private_key))
        except ValueError as exc:
            raise ChainError(
                "TRON transaction expired or the key is not in its permission list"
            ) from exc
        body = transaction.to_json()
        return SignedTransaction(
            chain=Chain.TRON,
            network=self.network,
            tx_hash=transaction.txid,
            raw=body,
            prepared=prepared,
        )

    def broadcast(self, signed: SignedTransaction) -> BroadcastReceipt:
        if signed.chain is not Chain.TRON:
            raise ChainError("signed transaction is not TRON")
        transaction = Transaction.from_json(signed.raw, client=self.client())
        try:
            result = self.client().broadcast(transaction)
        except Exception as exc:  # noqa: BLE001 - RPC refusal must remain typed
            raise ChainError(f"TRON broadcast failed: {exc}") from exc
        accepted = bool(result.get("result")) if isinstance(result, dict) else False
        if not accepted:
            raise ChainError(
                "TRON node refused the transaction: "
                f"{result.get('code') if isinstance(result, dict) else 'unknown'}"
            )
        return BroadcastReceipt(
            tx_hash=transaction.txid,
            accepted=True,
            detail={"endpoint": self.network.value, "result": result},
        )

    def confirmations(self, tx_hash: str) -> int:
        info = self.client().get_transaction_info(tx_hash)
        if not info or not info.get("blockNumber"):
            return 0
        latest = self.client().get_latest_block_number()
        return max(1, latest - int(info["blockNumber"]) + 1)
