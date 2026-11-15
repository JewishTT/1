"""EVM swap providers: Uniswap V3 on-chain quotes and 0x aggregator quotes.

Uniswap is quoted directly against QuoterV2, so the number came from the pool
that will fill the order rather than from a price screen. Native ETH is wrapped
and unwrapped inside one SwapRouter02 ``multicall``; token inputs carry the
approval the executor will perform first.

0x is optional and adds native/token coverage beyond the pools this adapter is
configured to know. It is attempted only when it answers; a missing API key or a
rate limit is reported as an unavailable provider, never as a bad price.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

from specops.cryptotx.chains.ethereum import EthereumAdapter
from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import RpcError, SwapError, SwapUnavailable
from specops.cryptotx.models import Asset, Chain, Network, SwapInstruction, SwapQuote
from specops.cryptotx.swaps.base import SwapProvider, SwapRequest

_WETH = {
    Network.MAINNET: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    Network.TESTNET: "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
}
_ETH_PLACEHOLDER = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
_FEE_TIERS = (500, 3000, 10000, 100)


def _selector(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


def _enc(signature: str, types: list[str], values: list[Any]) -> str:
    return _selector(signature) + abi_encode(types, values).hex()


def _token_address(asset: Asset, network: Network) -> str:
    if asset.native:
        return _WETH[network]
    if not asset.contract:
        raise SwapUnavailable(f"{asset.symbol} has no contract address")
    return to_checksum_address(asset.contract)


class UniswapProvider(SwapProvider):
    name = "uniswap"

    def __init__(
        self,
        config: CryptoTxConfig,
        adapter: EthereumAdapter,
        network: Network,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.network = network

    def supports(self, request: SwapRequest) -> bool:
        if request.from_chain is not Chain.ETHEREUM or request.to_chain is not Chain.ETHEREUM:
            return False
        if request.network is not self.network:
            return False
        if (
            not self.config.uniswap_router[self.network]
            or not self.config.uniswap_quoter[self.network]
        ):
            return False
        if request.from_asset.native and request.to_asset.native:
            return False
        return True

    def _quote_pool(self, token_in: str, token_out: str, amount_raw: int) -> tuple[int, int]:
        quoter = self.adapter.validate_address(self.config.uniswap_quoter[self.network] or "")
        best: tuple[int, int] | None = None
        for fee in _FEE_TIERS:
            data = _enc(
                "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
                ["(address,address,uint256,uint24,uint160)"],
                [(token_in, token_out, amount_raw, fee, 0)],
            )
            try:
                result = self.adapter.rpc.call(
                    "eth_call", [{"to": quoter, "data": data}, "latest"]
                )
            except RpcError:
                continue
            try:
                raw = bytes.fromhex(str(result).removeprefix("0x"))
                amount_out = int.from_bytes(raw[:32], "big")
            except (ValueError, TypeError):
                continue
            if amount_out <= 0:
                continue
            if best is None or amount_out > best[0]:
                best = (amount_out, fee)
        if best is None:
            raise SwapUnavailable("no Uniswap V3 pool answered for this pair")
        return best

    def _swap_calldata(
        self,
        request: SwapRequest,
        token_in: str,
        token_out: str,
        fee: int,
        amount_raw: int,
        min_raw: int,
    ) -> tuple[str, int, str]:
        router = self.adapter.validate_address(self.config.uniswap_router[self.network] or "")
        native_in = request.from_asset.native
        native_out = request.to_asset.native
        target = self.adapter.validate_address(request.to_address)
        recipient = router if native_out else target
        swap = _enc(
            "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",
            ["(address,address,uint24,address,uint256,uint256,uint160)"],
            [(token_in, token_out, fee, recipient, amount_raw, min_raw, 0)],
        )
        if native_in:
            return swap, amount_raw, router
        if native_out:
            unwrap = _enc(
                "unwrapWETH9(uint256,address)", ["uint256", "address"], [min_raw, target]
            )
            data = _enc(
                "multicall(bytes[])", ["bytes[]"],
                [[bytes.fromhex(swap[2:]), bytes.fromhex(unwrap[2:])]],
            )
            return data, 0, router
        return swap, 0, router

    def quote(self, request: SwapRequest) -> SwapQuote:
        if not self.supports(request):
            raise SwapUnavailable("Uniswap does not support this request")
        if request.from_chain is not request.to_chain:
            raise SwapUnavailable("Uniswap is a same-chain provider")
        try:
            token_in = _token_address(request.from_asset, self.network)
            token_out = _token_address(request.to_asset, self.network)
        except SwapUnavailable as exc:
            raise SwapUnavailable(str(exc)) from exc
        amount_raw = request.from_asset.to_base_units(request.amount)
        amount_out, fee = self._quote_pool(token_in, token_out, amount_raw)
        expected = request.to_asset.from_base_units(amount_out)
        min_out = request.minimum_out(expected)
        min_raw = int(min_out * (Decimal(10) ** request.to_asset.decimals))
        data, value, router = self._swap_calldata(
            request, token_in, token_out, fee, amount_raw, min_raw
        )
        instruction = SwapInstruction(
            kind="evm_call",
            chain=Chain.ETHEREUM,
            to=router,
            asset=request.from_asset.symbol,
            amount=request.amount,
            value=Decimal(value) / (Decimal(10) ** request.from_asset.decimals)
            if value else Decimal(0),
            calldata=data,
            description=(
                f"Uniswap V3 {request.from_asset.symbol}->{request.to_asset.symbol} "
                f"fee={fee}"
            ),
            approval_spender=None if request.from_asset.native else router,
            approval_asset=None if request.from_asset.native else request.from_asset.symbol,
            approval_amount=None if request.from_asset.native else str(request.amount),
            extra={"fee_tier": fee, "router": router, "gas": 350_000},
        )
        expires = (
            datetime.now(UTC) + timedelta(minutes=10)
        ).isoformat()
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
            route=(
                f"{request.from_asset.symbol}->{request.to_asset.symbol} "
                f"V3 fee {fee}"
            ),
            expires_at=expires,
            instruction=instruction,
            raw={"amount_out_raw": str(amount_out), "fee_tier": fee},
        )


class ZeroExProvider(SwapProvider):
    name = "zeroex"

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
        return (
            request.from_chain is Chain.ETHEREUM
            and request.to_chain is Chain.ETHEREUM
            and request.network is Network.MAINNET
        )

    def _sell_token(self, asset: Asset) -> str:
        return _ETH_PLACEHOLDER if asset.native else to_checksum_address(asset.contract or "")

    def quote(self, request: SwapRequest) -> SwapQuote:
        if not self.supports(request):
            raise SwapUnavailable("0x only routes Ethereum mainnet in this fabric")
        if to_checksum_address(request.to_address) != to_checksum_address(
            request.from_address
        ):
            raise SwapUnavailable("0x cannot redirect output to a third-party address")
        sell = self._sell_token(request.from_asset)
        buy = self._sell_token(request.to_asset)
        params = {
            "sellToken": sell,
            "buyToken": buy,
            "sellAmount": str(request.from_asset.to_base_units(request.amount)),
            "takerAddress": request.from_address,
            "slippagePercentage": str(request.slippage_bps / 100),
        }
        headers: dict[str, str] = {}
        if self.config.zeroex_api_key:
            headers["0x-api-key"] = self.config.zeroex_api_key
        try:
            response = self._client.get(
                self.config.zeroex_url.rstrip("/") + "/swap/v1/quote",
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise SwapError(f"0x quote failed: {exc}") from exc
        if response.status_code >= 400:
            raise SwapUnavailable(
                f"0x quote unavailable (HTTP {response.status_code})"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SwapError("0x quote is not JSON") from exc
        if not isinstance(body, dict) or not body.get("to") or not body.get("data"):
            raise SwapError("0x quote is missing its transaction")
        buy_raw = int(body.get("buyAmount", 0))
        min_raw = int(body.get("minBuyAmount", 0) or buy_raw)
        if buy_raw <= 0:
            raise SwapUnavailable("0x returned a zero-output quote")
        expected = request.to_asset.from_base_units(buy_raw)
        min_out = request.to_asset.from_base_units(min_raw)
        requested_min = request.minimum_out(expected)
        if min_out < requested_min:
            raise SwapUnavailable(
                f"0x quote minimum {min_out} is below the requested {requested_min}"
            )
        value = Decimal(int(body.get("value", 0) or 0)) / (Decimal(10) ** 18)
        allowance = body.get("allowanceTarget")
        if not request.from_asset.native and not allowance:
            raise SwapError("0x quote has no allowance target for a token sale")
        instruction = SwapInstruction(
            kind="evm_call",
            chain=Chain.ETHEREUM,
            to=to_checksum_address(str(body["to"])),
            asset=request.from_asset.symbol,
            amount=request.amount,
            value=value,
            calldata=str(body["data"]),
            description=f"0x {request.from_asset.symbol}->{request.to_asset.symbol}",
            approval_spender=None if request.from_asset.native
            else to_checksum_address(str(allowance)),
            approval_asset=None if request.from_asset.native
            else request.from_asset.symbol,
            approval_amount=None if request.from_asset.native else str(request.amount),
            extra={"gas": int(body.get("estimatedGas", 350_000) or 350_000)},
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
            route=(
                body.get("route")
                if isinstance(body.get("route"), str)
                else "0x aggregated route"
            ),
            expires_at=(
                datetime.now(UTC) + timedelta(minutes=5)
            ).isoformat(),
            instruction=instruction,
            raw=body,
        )
