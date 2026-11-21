"""SunSwap V2 quotes and calldata for TRON.

SunSwap is the TRON leg of the same-chain automation: quotes come from the
router's own ``getAmountsOut`` and the swap is encoded against the same router,
so quote and execution cannot drift onto different pools. Native TRX travels as
WTRX inside the path while the call still carries TRX as ``call_value``.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from eth_utils import keccak
from tronpy.abi import trx_abi
from tronpy.keys import is_base58check_address

from specops.cryptotx.chains.tron import TronAdapter
from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import SwapError, SwapUnavailable
from specops.cryptotx.models import Asset, Chain, Network, SwapInstruction, SwapQuote
from specops.cryptotx.swaps.base import SwapProvider, SwapRequest

_WTRX = {
    Network.MAINNET: "TNUC9Qb1rRpS5CbWLmNMxXBjyFoydXjWFR",
    Network.TESTNET: None,
}
_FEE_LIMIT_SUN = 30_000_000
_DEADLINE_S = 1200


def _selector(signature: str) -> str:
    return keccak(text=signature)[:4].hex()


def _encode(signature: str, types: str, values: list[object]) -> str:
    return _selector(signature) + trx_abi.encode_single(types, values).hex()


class SunSwapProvider(SwapProvider):
    name = "sunswap"

    def __init__(
        self,
        config: CryptoTxConfig,
        adapter: TronAdapter,
        network: Network,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.network = network

    def _wtrx(self) -> str:
        if self.network is Network.MAINNET:
            return _WTRX[Network.MAINNET]
        value = os.environ.get("CRYPTOTX_WTRX_TESTNET")
        if not value or not is_base58check_address(value):
            raise SwapUnavailable(
                "SunSwap on testnet needs CRYPTOTX_WTRX_TESTNET"
            )
        return value

    def _address(self, asset: Asset) -> str:
        if asset.native:
            return self._wtrx()
        if not asset.contract or not is_base58check_address(asset.contract):
            raise SwapUnavailable(f"{asset.symbol} has no TRC20 contract")
        return asset.contract

    def supports(self, request: SwapRequest) -> bool:
        if request.from_chain is not Chain.TRON or request.to_chain is not Chain.TRON:
            return False
        if request.network is not self.network:
            return False
        if not self.config.sunswap_router[self.network]:
            return False
        if request.from_asset.native and request.to_asset.native:
            return False
        return True

    def quote(self, request: SwapRequest) -> SwapQuote:
        if not self.supports(request):
            raise SwapUnavailable("SunSwap does not support this request")
        router = self.adapter.validate_address(
            self.config.sunswap_router[self.network] or ""
        )
        path = [self._address(request.from_asset), self._address(request.to_asset)]
        amount_raw = request.from_asset.to_base_units(request.amount)
        owner = self.adapter.validate_address(request.from_address)
        recipient = self.adapter.validate_address(request.to_address)
        parameter = trx_abi.encode_single(
            "(uint256,address[])", [amount_raw, path]
        ).hex()
        try:
            raw = self.adapter.client().trigger_const_smart_contract_function(
                owner, router, "getAmountsOut(uint256,address[])", parameter
            )
        except Exception as exc:  # noqa: BLE001
            raise SwapUnavailable(f"SunSwap quote failed: {exc}") from exc
        try:
            amounts = trx_abi.decode_single(
                "uint256[]", bytes.fromhex(str(raw).removeprefix("0x"))
            )
        except Exception as exc:  # noqa: BLE001
            raise SwapError("SunSwap returned an undecodable quote") from exc
        if len(amounts) < 2 or int(amounts[-1]) <= 0:
            raise SwapUnavailable("SunSwap returned a zero-output quote")
        expected = request.to_asset.from_base_units(int(amounts[-1]))
        min_out = request.minimum_out(expected)
        min_raw = int(min_out * (Decimal(10) ** request.to_asset.decimals))
        deadline = int(time.time()) + _DEADLINE_S
        if request.from_asset.native:
            data = _encode(
                "swapExactTRXForTokens(uint256,address[],address,uint256)",
                "(uint256,address[],address,uint256)",
                [min_raw, path, recipient, deadline],
            )
        elif request.to_asset.native:
            data = _encode(
                "swapExactTokensForTRX(uint256,uint256,address[],address,uint256)",
                "(uint256,uint256,address[],address,uint256)",
                [amount_raw, min_raw, path, recipient, deadline],
            )
        else:
            data = _encode(
                "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
                "(uint256,uint256,address[],address,uint256)",
                [amount_raw, min_raw, path, recipient, deadline],
            )
        instruction = SwapInstruction(
            kind="tron_call",
            chain=Chain.TRON,
            to=router,
            asset=request.from_asset.symbol,
            amount=request.amount,
            value=request.amount if request.from_asset.native else Decimal(0),
            calldata="0x" + data,
            fee_limit=_FEE_LIMIT_SUN,
            description=(
                f"SunSwap {request.from_asset.symbol}->{request.to_asset.symbol}"
            ),
            approval_spender=None if request.from_asset.native else router,
            approval_asset=None if request.from_asset.native else request.from_asset.symbol,
            approval_amount=None if request.from_asset.native else str(request.amount),
            extra={"router": router, "path": path, "deadline": deadline},
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
            route=f"SunSwap {request.from_asset.symbol}->{request.to_asset.symbol}",
            expires_at=(
                datetime.now(UTC) + timedelta(minutes=10)
            ).isoformat(),
            instruction=instruction,
            raw={"amounts_out_raw": [str(item) for item in amounts]},
        )

