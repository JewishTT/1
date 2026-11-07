"""THORChain cross-chain quotes for BTC and Ethereum.

THORChain is the automated BTC<->ETH leg because it settles natively on both
chains: a Bitcoin deposit is a plain transfer with an OP_RETURN memo, and an
Ethereum deposit is a call to the THORChain router with ``depositWithExpiry``.
No wrapped asset, no custodian and no off-chain order book.

The provider only quotes mainnet. THORChain's stagenet is a different network
with different vaults; pretending testnet funds could take this route would be
a lie the executor could not recover from.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import SwapError, SwapUnavailable
from specops.cryptotx.models import (
    Asset,
    Chain,
    Network,
    SwapInstruction,
    SwapQuote,
)
from specops.cryptotx.swaps.base import SwapProvider, SwapRequest

_ETH = Asset(Chain.ETHEREUM, "ETH", 18)
_BTC = Asset(Chain.BITCOIN, "BTC", 8)
_USDC_MAINNET = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
_DEFAULT_ROUTER = "0xD37BbE5744D730a1d98d8DC97c42F0Ca46aD7146"
_ETH_PLACEHOLDER = "0x0000000000000000000000000000000000000000"


def _thor_asset(asset: Asset, network: Network) -> str:
    if network is not Network.MAINNET:
        raise SwapUnavailable("THORChain quotes are mainnet-only in this fabric")
    if asset.chain is Chain.BITCOIN and asset.native:
        return "BTC.BTC"
    if asset.chain is Chain.ETHEREUM and asset.native:
        return "ETH.ETH"
    if (
        asset.chain is Chain.ETHEREUM
        and asset.contract
        and asset.contract.lower() == _USDC_MAINNET.lower()
    ):
        return f"ETH.USDC-{to_checksum_address(asset.contract)}"
    raise SwapUnavailable(f"THORChain does not route {asset.symbol} in this adapter")


def _selector(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


class ThorchainProvider(SwapProvider):
    name = "thorchain"

    def __init__(
        self,
        config: CryptoTxConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.Client(
            timeout=config.request_timeout_s, transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def supports(self, request: SwapRequest) -> bool:
        if request.network is not Network.MAINNET:
            return False
        if request.from_chain is request.to_chain:
            return False
        chains = {request.from_chain, request.to_chain}
        if not chains <= {Chain.BITCOIN, Chain.ETHEREUM}:
            return False
        try:
            _thor_asset(request.from_asset, request.network)
            _thor_asset(request.to_asset, request.network)
        except SwapUnavailable:
            return False
        return True

    def _quote_body(self, request: SwapRequest) -> dict[str, Any]:
        from_asset = _thor_asset(request.from_asset, request.network)
        to_asset = _thor_asset(request.to_asset, request.network)
        amount = request.from_asset.to_base_units(request.amount)
        params = {
            "from_asset": from_asset,
            "to_asset": to_asset,
            "amount": str(amount),
            "from_address": request.from_address,
            "to_address": request.to_address,
            "streaming_interval": "1",
            "streaming_quantity": "0",
        }
        last: Exception | None = None
        for _ in range(self.config.max_retries + 1):
            try:
                response = self._client.get(
                    self.config.thorchain_url.rstrip("/") + "/thorchain/quote/swap",
                    params=params,
                )
                if response.status_code >= 400:
                    raise SwapError(
                        f"THORChain quote returned HTTP {response.status_code}"
                    )
                body = response.json()
                if not isinstance(body, dict):
                    raise SwapError("THORChain quote is not an object")
                if body.get("error"):
                    raise SwapUnavailable(f"THORChain: {body['error']}")
                return body
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
        raise SwapError(f"THORChain quote failed: {last}")

    def quote(self, request: SwapRequest) -> SwapQuote:
        if not self.supports(request):
            raise SwapUnavailable("THORChain does not support this pair")
        body = self._quote_body(request)
        try:
            expected_raw = int(body["expected_amount_out"])
            inbound = str(body["inbound_address"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SwapError("THORChain quote is missing expected_amount_out or inbound") from exc
        if expected_raw <= 0:
            raise SwapUnavailable("THORChain returned a zero-output quote")
        from_thor = _thor_asset(request.from_asset, request.network)
        to_thor = _thor_asset(request.to_asset, request.network)
        memo = str(body.get("memo") or f"=:{to_thor}:{request.to_address}")
        expiry_raw = body.get("expiry")
        if isinstance(expiry_raw, (int, float)):
            expires = datetime.fromtimestamp(int(expiry_raw), UTC).isoformat()
            expiry_unix = int(expiry_raw)
        else:
            expiry_unix = int(
                (datetime.now(UTC) + timedelta(minutes=10)).timestamp()
            )
            expires = datetime.fromtimestamp(expiry_unix, UTC).isoformat()
        expected = request.to_asset.from_base_units(expected_raw)
        min_out = request.minimum_out(expected)
        fees = body.get("fees") if isinstance(body.get("fees"), dict) else {}
        fee_raw = int(fees.get("total", 0) or 0)
        fee_native = request.from_asset.from_base_units(fee_raw)
        route = f"{from_thor} -> {to_thor}"
        if request.from_chain is Chain.BITCOIN:
            instruction = SwapInstruction(
                kind="deposit",
                chain=Chain.BITCOIN,
                to=inbound,
                asset=request.from_asset.symbol,
                amount=request.amount,
                memo=memo,
                description=f"THORChain deposit {route}",
                extra={"inbound_address": inbound, "thor_from": from_thor,
                       "thor_to": to_thor},
            )
        else:
            router = to_checksum_address(
                str(body.get("router") or _DEFAULT_ROUTER)
            )
            amount_raw = request.from_asset.to_base_units(request.amount)
            calldata = _selector(
                "depositWithExpiry(address,address,uint256,string,uint256)"
            ) + abi_encode(
                ["address", "address", "uint256", "string", "uint256"],
                [
                    to_checksum_address(inbound),
                    _ETH_PLACEHOLDER if request.from_asset.native
                    else to_checksum_address(request.from_asset.contract or ""),
                    amount_raw,
                    memo,
                    expiry_unix,
                ],
            ).hex()
            instruction = SwapInstruction(
                kind="evm_call",
                chain=Chain.ETHEREUM,
                to=router,
                asset=request.from_asset.symbol,
                amount=request.amount,
                value=request.amount if request.from_asset.native else Decimal(0),
                calldata=calldata,
                description=f"THORChain router deposit {route}",
                approval_spender=None if request.from_asset.native else router,
                approval_asset=None if request.from_asset.native
                else request.from_asset.symbol,
                approval_amount=None if request.from_asset.native
                else str(request.amount),
                extra={"vault": inbound, "router": router, "thor_from": from_thor,
                       "thor_to": to_thor, "expiry": expires},
            )
        return SwapQuote(
            provider=self.name,
            from_chain=request.from_chain,
            to_chain=request.to_chain,
            from_asset=request.from_asset.symbol,
            to_asset=request.to_asset.symbol,
            amount_in=request.amount,
            expected_amount_out=expected,
            min_amount_out=min_out,
            from_address=request.from_address,
            to_address=request.to_address,
            route=route,
            expires_at=expires,
            instruction=instruction,
            raw=body,
            fee_native=fee_native,
            fee_asset=request.from_asset.symbol,
        )
