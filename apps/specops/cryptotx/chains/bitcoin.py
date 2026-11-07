"""Bitcoin adapter: BIP84 P2WPKH, UTXO selection, PSBT signing and Esplora.

The adapter signs real Bitcoin transactions locally. UTXOs and fee estimates
come from a block explorer (Esplora by default, or any compatible endpoint via
``CRYPTOTX_BTC_*_URL``). Coin selection is deterministic largest-first with a
fee recomputation per input count; change below the dust threshold is folded
into the miner fee rather than emitted as an unspendable output.

Only the wallet's own single derived address is swept. That is the honest scope
of a one-address wallet: a UTXO at another derivation is not silently spent.
"""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from typing import Any

import httpx
from embit import ec, script
from embit import transaction as embit_tx
from embit.networks import NETWORKS
from embit.psbt import PSBT

from specops.cryptotx import hd
from specops.cryptotx.chains.base import BroadcastReceipt, ChainAdapter
from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import ChainError, RpcError
from specops.cryptotx.models import (
    Asset,
    Chain,
    Network,
    PreparedTransaction,
    SignedTransaction,
    SwapInstruction,
)

_NETWORKS = {Network.MAINNET: NETWORKS["main"], Network.TESTNET: NETWORKS["test"]}
_PREFIXES = {
    Network.MAINNET: ("bc1", "1", "3"),
    Network.TESTNET: ("tb1", "m", "n", "2"),
}
_DUST_SATS = 546
_SATS = Decimal(10) ** 8


def _op_return_script(memo: str) -> bytes:
    payload = memo.encode("utf-8")
    if not payload:
        raise ChainError("memo is empty")
    if len(payload) > 80:
        raise ChainError("OP_RETURN memo exceeds 80 bytes")
    if len(payload) <= 75:
        return bytes([0x6A, len(payload)]) + payload
    return bytes([0x6A, 0x4C, len(payload)]) + payload


def _display_txid(raw_tx: embit_tx.Transaction) -> str:
    return raw_tx.txid()[::-1].hex()


class EsploraClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = max(0, retries)
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> Any:
        last: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                response = self._client.get(self.base_url + path)
                if response.status_code >= 400:
                    raise RpcError(f"Esplora GET {path} returned HTTP {response.status_code}")
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
        raise RpcError(f"Esplora GET {path} failed: {last}")

    def utxos(self, address: str) -> list[dict[str, Any]]:
        data = self._get(f"/address/{address}/utxo")
        if not isinstance(data, list):
            raise RpcError("Esplora UTXO response is not a list")
        return data

    def fee_rate(self, target_blocks: int = 6) -> Decimal:
        data = self._get("/fee-estimates")
        if not isinstance(data, dict) or not data:
            raise RpcError("Esplora fee-estimates is empty")
        for key in (str(target_blocks), "6", "3", "1"):
            if key in data:
                return max(Decimal(1), Decimal(str(data[key])))
        return max(Decimal(1), Decimal(str(next(iter(data.values())))))

    def tip_height(self) -> int:
        try:
            response = self._client.get(self.base_url + "/blocks/tip/height")
            response.raise_for_status()
            return int(response.text.strip())
        except (httpx.HTTPError, ValueError) as exc:
            raise RpcError("could not read Esplora tip height") from exc

    def status(self, txid: str) -> dict[str, Any]:
        return self._get(f"/tx/{txid}/status")

    def broadcast(self, raw_hex: str) -> str:
        try:
            response = self._client.post(
                self.base_url + "/tx", content=raw_hex.encode("ascii"),
                headers={"Content-Type": "text/plain"},
            )
        except httpx.HTTPError as exc:
            raise ChainError(f"Bitcoin broadcast failed: {exc}") from exc
        if response.status_code >= 400:
            raise ChainError(f"Bitcoin node refused the transaction: {response.text[:200]}")
        return response.text.strip()


class BitcoinAdapter(ChainAdapter):
    chain = Chain.BITCOIN

    def __init__(
        self,
        config: CryptoTxConfig,
        network: Network,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.network = network
        self.explorer = EsploraClient(
            config.btc_esplora[network],
            timeout=config.request_timeout_s,
            retries=config.max_retries,
            transport=transport,
        )

    def close(self) -> None:
        self.explorer.close()

    def native_asset(self) -> Asset:
        return Asset(Chain.BITCOIN, "BTC", 8)

    def validate_address(self, address: str) -> str:
        prefix = _PREFIXES[self.network]
        if not address.lower().startswith(prefix):
            raise ChainError(
                f"Bitcoin {self.network.value} address must start with one of {prefix}"
            )
        try:
            script.address_to_scriptpubkey(address)
        except Exception as exc:  # noqa: BLE001 - library refusal is the boundary
            raise ChainError(f"invalid Bitcoin address: {address!r}") from exc
        return address

    def get_balance(self, address: str, asset: Asset) -> Decimal:
        if not asset.native:
            raise ChainError("the Bitcoin adapter only tracks BTC")
        address = self.validate_address(address)
        total = sum(int(item.get("value", 0)) for item in self.explorer.utxos(address))
        return Decimal(total) / _SATS

    def _select(
        self,
        utxos: list[dict[str, Any]],
        amount_sats: int,
        rate: Decimal,
        output_count: int,
        memo_bytes: int,
    ) -> tuple[list[dict[str, Any]], int, int, bool]:
        usable = [u for u in utxos if int(u.get("value", 0)) > 0]
        if not usable:
            raise ChainError("no spendable UTXOs at the wallet address")
        usable.sort(key=lambda u: int(u["value"]), reverse=True)
        selected: list[dict[str, Any]] = []
        total = 0
        while usable:
            item = usable.pop(0)
            selected.append(item)
            total += int(item["value"])
            if total < amount_sats:
                continue
            vsize_with_change = (
                11
                + 68 * len(selected)
                + 31 * (output_count + 1)
                + (11 + memo_bytes if memo_bytes else 0)
            )
            fee_with_change = int(math.ceil(float(rate) * vsize_with_change))
            change = total - amount_sats - fee_with_change
            if change > _DUST_SATS:
                return selected, fee_with_change, change, True
            vsize_no_change = vsize_with_change - 31
            fee_no_change = int(math.ceil(float(rate) * vsize_no_change))
            if total >= amount_sats + fee_no_change:
                return selected, total - amount_sats, 0, False
        raise ChainError("insufficient BTC: UTXOs do not cover amount plus fee")

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
        if not asset.native:
            raise ChainError("the Bitcoin adapter only sends BTC")
        to_address = self.validate_address(to_address)
        source_address = self.validate_address(material.address)
        amount_sats = asset.to_base_units(amount)
        if amount_sats <= 0:
            raise ChainError("amount must be positive")
        rate = fee_rate or kwargs.get("sat_per_vbyte")
        utxos = kwargs.get("utxos")
        if utxos is None:
            utxos = self.explorer.utxos(source_address)
        if rate is None:
            rate = self.explorer.fee_rate(int(kwargs.get("fee_target_blocks", 6)))
        rate = Decimal(rate)
        if rate <= 0:
            raise ChainError("fee rate must be positive")
        memo_script = _op_return_script(memo) if memo else b""
        selected, fee_sats, change_sats, _has_change = self._select(
            list(utxos), amount_sats, rate,
            output_count=1, memo_bytes=len(memo_script),
        )
        destination_script = script.address_to_scriptpubkey(to_address)
        source_script = script.address_to_scriptpubkey(source_address)
        vins = [
            embit_tx.TransactionInput(
                bytes.fromhex(str(item["txid"]))[::-1],
                int(item["vout"]),
                sequence=0xFFFFFFFD,
            )
            for item in selected
        ]
        vouts = [embit_tx.TransactionOutput(amount_sats, destination_script)]
        if memo_script:
            vouts.append(embit_tx.TransactionOutput(0, script.Script(memo_script)))
        if change_sats > 0:
            vouts.append(embit_tx.TransactionOutput(change_sats, source_script))
        raw_tx = embit_tx.Transaction(version=2, vin=vins, vout=vouts)
        txid = _display_txid(raw_tx)
        payload = {
            "unsigned_hex": raw_tx.serialize().hex(),
            "txid": txid,
            "inputs": [
                {
                    "txid": str(item["txid"]),
                    "vout": int(item["vout"]),
                    "value": int(item["value"]),
                    "scriptpubkey": source_script.data.hex(),
                }
                for item in selected
            ],
            "memo": memo,
            "fee_rate_sat_vb": str(rate),
            "change_sats": change_sats,
        }
        return PreparedTransaction(
            chain=Chain.BITCOIN,
            network=self.network,
            from_address=source_address,
            to_address=to_address,
            asset=asset,
            amount=amount,
            fee=Decimal(fee_sats) / _SATS,
            payload=payload,
            description=f"send {amount} BTC" + (" with memo" if memo else ""),
            tx_hash=txid,
            fee_detail={
                "inputs": len(selected),
                "fee_sats": fee_sats,
                "change_sats": change_sats,
                "fee_rate_sat_vb": str(rate),
            },
        )

    def prepare_call(
        self,
        material: hd.DerivedKey,
        instruction: SwapInstruction,
        *,
        asset: Asset,
    ) -> PreparedTransaction:
        if not instruction.memo:
            raise ChainError("Bitcoin deposit instructions require a memo")
        return self.prepare_transfer(
            material,
            instruction.to,
            asset,
            instruction.amount,
            memo=instruction.memo,
            fee_rate=None,
        )

    def sign(self, prepared: PreparedTransaction, material: hd.DerivedKey) -> SignedTransaction:
        if prepared.chain is not Chain.BITCOIN:
            raise ChainError("prepared transaction is not Bitcoin")
        raw_tx = embit_tx.Transaction.parse(bytes.fromhex(prepared.payload["unsigned_hex"]))
        psbt = PSBT(raw_tx)
        inputs = prepared.payload.get("inputs", [])
        if len(inputs) != len(raw_tx.vin):
            raise ChainError("PSBT input metadata does not match the transaction")
        for index, item in enumerate(inputs):
            utxo = embit_tx.TransactionOutput(
                int(item["value"]), script.Script(bytes.fromhex(item["scriptpubkey"]))
            )
            psbt.inputs[index].witness_utxo = utxo
        private_key = ec.PrivateKey(material.private_key)
        try:
            signed_count = psbt.sign_with(private_key)
        except Exception as exc:  # noqa: BLE001 - library boundary
            raise ChainError("embit refused to sign the PSBT") from exc
        if signed_count != len(raw_tx.vin):
            raise ChainError(
                f"PSBT signed {signed_count} of {len(raw_tx.vin)} input(s); "
                "UTXOs may not belong to this wallet"
            )
        final_tx = psbt.tx
        for index, inp in enumerate(psbt.inputs):
            if inp.final_scriptwitness is None:
                partial = list(inp.partial_sigs.items())
                if not partial:
                    raise ChainError(f"input {index} has no signature to finalize")
                pubkey, sig = partial[0]
                inp.final_scriptwitness = script.Witness([sig, pubkey.serialize()])
            final_tx.vin[index].witness = inp.final_scriptwitness
        raw_hex = final_tx.serialize().hex()
        txid = _display_txid(final_tx)
        return SignedTransaction(
            chain=Chain.BITCOIN,
            network=self.network,
            tx_hash=txid,
            raw=raw_hex,
            prepared=prepared,
        )

    def broadcast(self, signed: SignedTransaction) -> BroadcastReceipt:
        if signed.chain is not Chain.BITCOIN:
            raise ChainError("signed transaction is not Bitcoin")
        txid = self.explorer.broadcast(str(signed.raw))
        return BroadcastReceipt(
            tx_hash=txid or signed.tx_hash,
            accepted=True,
            detail={"endpoint": self.network.value},
        )

    def confirmations(self, tx_hash: str) -> int:
        try:
            status = self.explorer.status(tx_hash)
        except RpcError:
            return 0
        if not status.get("confirmed"):
            return 0
        height = int(status.get("block_height", 0))
        tip = self.explorer.tip_height()
        return max(1, tip - height + 1)


def witness_commitment(raw_hex: str) -> str:
    """A cheap integrity check used by the executor before broadcasting."""
    return hashlib.sha256(bytes.fromhex(raw_hex)).hexdigest()
